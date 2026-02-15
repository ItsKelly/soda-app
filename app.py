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
    /* תיקון ליישור טאבים */
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
        # TTL של 10 שניות לאיזון בין יציבות לבין מהירות עדכון
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
        
        # שליפת מחיר בקבוק
        try:
            price_row = s_df[s_df['key'] == 'bottle_price']
            price = float(price_row['value'].values[0]) if not price_row.empty else 2.5
        except:
            price = 2.5
            
        return u_df, t_df, price, i_df
    except Exception as e:
        st.error(f"שגיאת תקשורת: {e}")
        return pd.DataFrame(), pd.DataFrame(), 2.5, pd.DataFrame()

users_df, trans_df, bottle_price, inv_df = get_all_data()

# --- 4. לוגיקת התחברות אוטומטית (Persistent Login) ---
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
        user_list = users_df["name"].tolist() if not users_df.empty else ["טוען..."]
        user_name = st.selectbox("בחר שם", user_list)
        user_pin = st.text_input("קוד אישי (4 ספרות)", type="password")
        if st.form_submit_button("כניסה"):
            user_match = users_df[users_df["name"] == user_name]
            if not user_match.empty and str(user_pin).strip() == user_match.iloc[0]["pin"]:
                user_data = user_match.iloc[0].to_dict()
                st.session_state.user = user_data
                # שמירת עוגיה ל-30 יום
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
    
    tabs_labels = ["👤 המועדון שלי"]
    if is_admin:
        tabs_labels.append("🛠️ ניהול")
    
    selected_tabs = st.tabs(tabs_labels)

    # --- טאב אישי ---
    with selected_tabs[0]:
        st.title(f"שלום, {user['name']} 👋")
        
        # חישוב חוב (רק תשלומים שאושרו)
        u_trans = trans_df[trans_df["email"] == user["email"]]
        total_spent = u_trans[u_trans["type"] == "purchase"]["amount"].astype(float).sum()
        total_paid = u_trans[(u_trans["type"] == "payment") & (u_trans["status"] == "completed")]["amount"].astype(float).sum()
        pending_paid = u_trans[(u_trans["type"] == "payment") & (u_trans["status"] == "pending")]["amount"].astype(float).sum()
        
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
                    "email": user["email"],
                    "type": "purchase",
                    "amount": bottle_price,
                    "status": "completed"
                }])
                conn.update(worksheet="Transactions", data=pd.concat([trans_df
