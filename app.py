import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import extra_streamlit_components as stx

# --- 1. הגדרות עמוד ותמיכה בעברית (RTL) ---
st.set_page_config(page_title="מועדון סודה PRO", layout="centered")

st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stForm"] { direction: rtl; }
    .stButton>button { width: 100%; border-radius: 8px; }
    [data-testid="stMetricValue"] { font-size: 28px; color: #1E88E5; }
    .stTabs [data-baseweb="tab-list"] { direction: rtl; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ניהול עוגיות (Login עמיד) ---
# הגדרה ללא cache כדי למנוע CachedWidgetWarning
cookie_manager = stx.CookieManager()

# --- 3. חיבור וטעינת נתונים ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_all_data():
    try:
        # טעינת כל הטאבים עם TTL של 10 שניות לאיזון עומסים
        u_df = conn.read(worksheet="Users", ttl="10s").fillna("")
        t_df = conn.read(worksheet="Transactions", ttl="10s").fillna("")
        s_df = conn.read(worksheet="Settings", ttl="10s").fillna("")
        i_df = conn.read(worksheet="Inventory", ttl="10s").fillna(0)
        
        # ניקוי נתונים בסיסי
        u_df['name'] = u_df['name'].astype(str).str.strip()
        u_df['email'] = u_df['email'].astype(str).str.strip()
        u_df['pin'] = u_df['pin'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        t_df['amount'] = pd.to_numeric(t_df['amount'], errors='coerce').fillna(0)
        i_df['quantity'] = pd.to_numeric(i_df['quantity'], errors='coerce').fillna(0)
        
        # שליפת מחיר בקבוק מהגדרות
        try:
            price_row = s_df[s_df['key'] == 'bottle_price']
            price = float(price_row['value'].values[0]) if not price_row.empty else 2.5
        except:
            price = 2.5
            
        return u_df, t_df, price, i_df
    except Exception as e:
        st.error(f"שגיאת טעינה: {e}")
        return pd.DataFrame(), pd.DataFrame(), 2.5, pd.DataFrame()

users_df, trans_df, bottle_price, inv_df = get_all_data()

# --- 4. לוגיקת התחברות אוטומטית (עוגיות) ---
if "user" not in st.session_state:
    saved_email = cookie_manager.get(cookie="soda_user_email")
    if saved_email and not users_df.empty:
        user_match = users_df[users_df["email"] == saved_email]
        if not user_match.empty:
            st.session_state.user = user_match.iloc[0].to_dict()
            st.rerun()

# --- 5. ממשק משתמש ---
if "user" not in st.session_state:
    # --- מסך כניסה ---
    st.header("🥤 מועדון סודה - כניסה")
    with st.form("login_form"):
        user_list = users_df["name"].tolist() if not users_df.empty else ["טוען משתמשים..."]
        user_name = st.selectbox("בחר שם", user_list)
        user_pin = st.text_input("קוד אישי (4 ספרות)", type="password")
        if st.form_submit_button("כניסה"):
            user_match = users_df[users_df["name"] == user_name]
            if not user_match.empty and str(user_pin).strip() == user_match.iloc[0]["pin"]:
                user_data = user_match.iloc[0].to_dict()
                st.session_state.user = user_data
                # שמירת עוגיה לשנה
                cookie_manager.set("soda_user_email", user_data['email'], 
                                 expires_at=datetime.now().replace(year=datetime.now().year + 1))
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("פרטים שגויים, נסה שוב.")
else:
    # --- ממשק משתמש מחובר ---
    user = st.session_state.user
    is_admin = user.get('role') == 'admin'
    
    # הגדרת טאבים
    if is_admin:
        tabs = st.tabs(["👤 המועדון שלי", "🛠️ ניהול"])
    else:
        tabs = [st.container()]

    # --- טאב אישי ---
    with tabs[0]:
        st.title(f"שלום, {user['name']} 👋")
        
        # חישוב חוב (רק רכישות פחות תשלומים שאושרו)
        u_trans = trans_df[trans_df["email"] == user["email"]]
        total_spent = u_trans[u_trans["type"] == "purchase"]["amount"].sum()
        total_paid = u_trans[(u_trans["type"] == "payment") & (u_trans["status"] == "completed")]["amount"].sum()
        pending_paid = u_trans[(u_trans["type"] == "payment") & (u_trans["status"] == "pending")]["amount"].sum()
        balance = total_spent - total_paid
        
        c1, c2, c3 = st.columns(3)
        c1.metric("חוב לתשלום", f"₪{balance:.2f}")
        c2.metric("מחיר בקבוק", f"₪{bottle_price}")
        if pending_paid > 0:
            c3.warning(f"באישור: ₪{pending_paid}")

        st.divider()

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🥤 לקחתי בקבוק"):
                new_row = pd.DataFrame([{
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "email": user["email"], "type": "purchase", 
                    "amount": bottle_price, "status": "completed"
                }])
                conn.update(worksheet="Transactions", data=pd.concat([trans_df, new_row], ignore_index=True))
                st.cache_data.clear()
                st.success("לרוויה!")
                st.rerun()
        
        with col_b:
            with st.popover("💰 דיווחתי על תשלום"):
                amt = st.number_input("סכום ששולם", min_value=1.0, step=1.0)
                if st.button("שלח דיווח"):
                    new_row = pd.DataFrame([{
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "email": user["email"], "type": "payment", 
                        "amount": amt, "status": "pending"
                    }])
                    conn.update(worksheet="Transactions", data=pd.concat([trans_df, new_row], ignore_index=True))
                    st.cache_data.clear()
                    st.info("נשלח לאישור מנהל.")
                    st.rerun()

        st.subheader("היסטוריה אישית")
        if not u_trans.empty:
            st.dataframe(u_trans.sort_values("timestamp", ascending=False), use_container_width=True)
        
        if st.button("🚪 התנתק והסר מהמכשיר"):
            cookie_manager.delete("soda_user_email")
            del st.session_state.user
            st.rerun()

    # --- טאב ניהול ---
    if is_admin:
        with tabs[1]:
            st.header("ממשק מנהל")
            
            # 1. אישור תשלומים
            st.subheader("💳 תשלומים הממתינים לאישור")
            pending = trans_df[trans_df["status"] == "pending"]
            if not pending.empty:
                for idx, row in pending.iterrows():
                    u_info = users_df[users_df["email"] == row["email"]]
                    u_n = u_info["name"].iloc[0] if not u_info.empty else "לא ידוע"
                    cp1, cp2 = st.columns([3, 1])
                    cp1.write(f"**{u_n}** - ₪{row['amount']} ({row['timestamp']})")
                    if cp2.button("אשר", key=f"app_{idx}"):
                        trans_df.at[idx, "status"] = "completed"
                        conn.update(worksheet="Transactions", data=trans_df)
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.write("אין תשלומים שמחכים לאישור.")

            st.divider()

            # 2. הוספת משתמש חדש
            with st.expander("👤 הוספת משתמש חדש"):
                with st.form("add_user_form"):
                    n_name = st.text_input("שם מלא")
                    n_email = st.text_input("אימייל (מזהה ייחודי)")
                    n_pin = st.text_input("קוד (4 ספרות)")
                    n_role = st.selectbox("תפקיד", ["user", "admin"])
                    if st.form_submit_button("הוסף למערכת"):
                        if n_name and n_email and len(n_pin) == 4:
                            new_u = pd.DataFrame([{"name": n_name, "email": n_email, "pin": n_pin, "role": n_role}])
                            conn.update(worksheet="Users", data=pd.concat([users_df, new_u], ignore_index=True))
                            st.cache_data.clear()
                            st.success(f"המשתמש {n_name} נוסף!")
                            st.rerun()
                        else:
                            st.error("מלא את כל הפרטים (קוד חייב להיות 4 ספרות).")

            st.divider()

            # 3. מלאי והגדרות
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.subheader("מלאי")
                total_in = inv_df['quantity'].sum()
                total_out = len(trans_df[trans_df['type'] == 'purchase'])
                st.metric("בקבוקים במקרר", int(total_in - total_out))
                with st.popover("➕ הוסף מלאי"):
                    q = st.number_input("כמות שהגיעה", min_value=1, value=24)
                    if st.button("עדכן מלאי"):
                        new_inv = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "quantity": q}])
                        conn.update(worksheet="Inventory", data=pd.concat([inv_df, new_inv], ignore_index=True))
                        st.cache_data.clear()
                        st.rerun()
            
            with col_m2:
                st.subheader("מחיר")
                new_p = st.number_input("עדכן מחיר בקבוק", value=bottle_price, step=0.5)
                if st.button("שמור מחיר"):
                    s_df_new = conn.read(worksheet="Settings", ttl=0)
                    if not s_df_new[s_df_new['key'] == 'bottle_price'].empty:
                        s_df_new.loc[s_df_new['key'] == 'bottle_price', 'value'] = new_p
                    else:
                        s_df_new = pd.concat([s_df_new, pd.DataFrame([{"key": "bottle_price", "value": new_p}])])
                    conn.update(worksheet="Settings", data=s_df_new)
                    st.cache_data.clear()
                    st.rerun()

            st.subheader("טבלת חובות כללית")
            summary = []
            for _, u in users_df.iterrows():
                ut = trans_df[trans_df["email"] == u["email"]]
                deb = ut[ut["type"] == "purchase"]["amount"].sum() - ut[(ut["type"] == "payment") & (ut["status"] == "completed")]["amount"].sum()
                summary.append({"שם": u["name"], "חוב": f"₪{deb:.2f}"})
            st.table(pd.DataFrame(summary).sort_values("חוב", ascending=False))
