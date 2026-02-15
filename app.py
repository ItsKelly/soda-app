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
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
    [data-testid="stMetricValue"] { font-size: 28px; color: #1E88E5; }
    .stTabs [data-baseweb="tab-list"] { direction: rtl; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ניהול עוגיות (Login עמיד) ---
cookie_manager = stx.CookieManager()

# --- 3. חיבור וטעינת נתונים ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_all_data():
    try:
        u_df = conn.read(worksheet="Users", ttl="10s").fillna("")
        t_df = conn.read(worksheet="Transactions", ttl="10s").fillna("")
        s_df = conn.read(worksheet="Settings", ttl="10s").fillna("")
        i_df = conn.read(worksheet="Inventory", ttl="10s").fillna(0)
        
        u_df['name'] = u_df['name'].astype(str).str.strip()
        u_df['email'] = u_df['email'].astype(str).str.strip()
        u_df['pin'] = u_df['pin'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        t_df['amount'] = pd.to_numeric(t_df['amount'], errors='coerce').fillna(0)
        i_df['quantity'] = pd.to_numeric(i_df['quantity'], errors='coerce').fillna(0)
        
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

# --- 4. לוגיקת התחברות אוטומטית ---
if "user" not in st.session_state:
    saved_email = cookie_manager.get(cookie="soda_user_email")
    if saved_email and not users_df.empty:
        user_match = users_df[users_df["email"] == saved_email]
        if not user_match.empty:
            st.session_state.user = user_match.iloc[0].to_dict()
            st.rerun()

# --- 5. ממשק משתמש ---
if "user" not in st.session_state:
    st.header("🥤 מועדון סודה - כניסה")
    with st.form("login_form"):
        user_list = users_df["name"].tolist() if not users_df.empty else ["טוען..."]
        user_name = st.selectbox("בחר שם מהרשימה", user_list)
        user_pin = st.text_input("קוד אישי", type="password")
        if st.form_submit_button("כניסה"):
            user_match = users_df[users_df["name"] == user_name]
            if not user_match.empty and str(user_pin).strip() == user_match.iloc[0]["pin"]:
                user_data = user_match.iloc[0].to_dict()
                st.session_state.user = user_data
                cookie_manager.set("soda_user_email", user_data['email'], expires_at=datetime)

