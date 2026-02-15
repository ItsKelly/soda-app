import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import extra_streamlit_components as stx

# --- 1. הגדרות עמוד ותמיכה בעברית (RTL) ---
st.set_page_config(page_title="מועדון סודה PRO", layout="centered")

# פונקציה להזרקת CSS עבור RTL
st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stForm"] { direction: rtl; }
    .stButton>button { width: 100%; border-radius: 8px; }
    [data-testid="stMetricValue"] { font-size: 28px; color: #1E88E5; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ניהול עוגיות (Persistent Login) ---
@st.cache_resource
def get_cookie_manager():
    return stx.CookieManager()

cookie_manager = get_cookie_manager()

# --- 3. חיבור וטעינת נתונים ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_all_data():
    try:
        u_df = conn.read(worksheet="Users", ttl="10s").fillna("")
        t_df = conn.read(worksheet="Transactions", ttl="10s").fillna("")
        s_df = conn.read(worksheet="Settings", ttl="10s").fillna("")
        i_df = conn.read(worksheet="Inventory", ttl="10s").fillna(0)
        
        u_df['name'] = u_df['name'].astype(str).str.strip()
        u_df['pin'] = u_df['pin'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        
        try:
            price = float(s_df[s_df['key'] == 'bottle_price']['value'].values[0])
        except: price = 2.5
            
        return u_df, t_df, price, i_df
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), 2.5, pd.DataFrame()

users_df, trans_df, bottle_price, inv_df = get_all_data()

# --- 4. לוגיקת התחברות אוטומטית (עוגיות) ---
if "user" not in st.session_state:
    saved_user_email = cookie_manager.get(cookie="soda_user_email")
    if saved_user_email:
        user_match = users_df[users_df["email"] == saved_user_email]
        if not user_match.empty:
            st.session_state.user = user_match.iloc[0].to_dict()
            st.rerun()

# --- 5. מסך כניסה או ממשק משתמש ---
if "user" not in st.session_state:
    st.header("🥤 מועדון סודה - כניסה")
    with st.form("login_form"):
        user_name = st.selectbox("מי אתה?", users_df["name"].tolist() if not users_df.empty else ["טוען..."])
        user_pin = st.text_input("קוד אישי", type="password")
        if st.form_submit_button("כניסה"):
            user_match = users_df[users_df["name"] == user_name]
            if not user_match.empty and str(user_pin).strip() == user_match.iloc[0]["pin"]:
                user_data = user_match.iloc[0].to_dict()
                st.session_state.user = user_data
                # שמירת עוגיה ל-30 יום
                cookie_manager.set("soda_user_email", user_data['email'], expires_at=datetime.now().replace(year=datetime.now().year + 1))
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("פרטים שגויים")
else:
    user = st.session_state.user
    is_admin = user.get('role') == 'admin'
    
    tabs_labels = ["👤 המועדון שלי"]
    if is_admin: tabs_labels.append("🛠️ ניהול")
    selected_tabs = st.tabs(tabs_labels)

    # --- טאב אישי ---
    with selected_tabs[0]:
        st.title(f"שלום, {user['name']} 👋")
        u_trans = trans_df[trans_df["email"] == user["email"]]
        total_spent = u_trans[u_trans["type"] == "purchase"]["amount"].astype(float).sum()
        total_paid = u_trans[(u_trans["type"] == "payment") & (u_trans["status"] == "completed")]["amount"].astype(float).sum()
        balance = total_spent - total_paid
        
        st.metric("חוב לתשלום", f"₪{balance:.2f}")
        
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🥤 לקחתי בקבוק"):
                new_row = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": user["email"], "type": "purchase", "amount": bottle_price, "status": "completed"}])
                conn.update(worksheet="Transactions", data=pd.concat([trans_df, new_row], ignore_index=True))
                st.cache_data.clear()
                st.rerun()
        with col_b:
            with st.popover("💰 דיווחתי על תשלום"):
                amt = st.number_input("סכום", min_value=1.0, step=1.0)
                if st.button("שלח"):
                    new_row = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": user["email"], "type": "payment", "amount": amt, "status": "pending"}])
                    conn.update(worksheet="Transactions", data=pd.concat([trans_df, new_row], ignore_index=True))
                    st.cache_data.clear()
                    st.rerun()

        if st.button("🚪 התנתק מכל המכשירים"):
            cookie_manager.delete("soda_user_email")
            del st.session_state.user
            st.rerun()

    # --- טאב ניהול ---
    if is_admin:
        with selected_tabs[1]:
            # חלק א: אישור תשלומים
            st.subheader("💳 אישור תשלומים")
            pending = trans_df[trans_df["status"] == "pending"]
            if not pending.empty:
                for idx, row in pending.iterrows():
                    u_n = users_df[users_df["email"] == row["email"]]["name"].iloc[0]
                    c_p1, c_p2 = st.columns([3, 1])
                    c_p1.write(f"**{u_n}**: ₪{row['amount']}")
                    if c_p2.button("אשר", key=f"app_{idx}"):
                        trans_df.at[idx, "status"] = "completed"
                        conn.update(worksheet="Transactions", data=trans_df)
                        st.cache_data.clear()
                        st.rerun()
            
            st.divider()

            # חלק ב: הוספת משתמש חדש
            with st.expander("👤 הוספת משתמש חדש למערכת"):
                with st.form("add_user_form"):
                    n_name = st.text_input("שם מלא")
                    n_email = st.text_input("אימייל (חייב להיות ייחודי)")
                    n_pin = st.text_input("קוד אישי (4 ספרות)")
                    n_role = st.selectbox("תפקיד", ["user", "admin"])
                    if st.form_submit_button("הוסף משתמש"):
                        if n_name and n_email and len(n_pin) == 4:
                            new_u = pd.DataFrame([{"name": n_name, "email": n_email, "pin": n_pin, "role": n_role}])
                            conn.update(worksheet="Users", data=pd.concat([users_df, new_u], ignore_index=True))
                            st.cache_data.clear()
                            st.success(f"המשתמש {n_name} נוסף!")
                            st.rerun()
                        else: st.error("מלא את כל הפרטים כנדרש")

            # חלק ג: הגדרות ומלאי
            st.divider()
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.write(f"**מחיר נוכחי:** ₪{bottle_price}")
                # (כאן אפשר להוסיף את עדכון המחיר מהקוד הקודם)
            with col_s2:
                in_stock = inv_df['quantity'].sum() - len(trans_df[trans_df['type'] == 'purchase'])
                st.write(f"**מלאי במקרר:** {int(in_stock)}")
