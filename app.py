import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from streamlit_google_auth import Authenticate
from datetime import datetime
import time

# -----------------------------------------------------------------------------
# 1. CONFIGURATION (חייב להיות ראשון!)
# -----------------------------------------------------------------------------
st.set_page_config(page_title="ניהול סודה", page_icon="🥤", layout="wide")

# עיצוב RTL
st.markdown("""<style>.stApp { direction: rtl; } h1,h2,h3,p,div { text-align: right; }</style>""", unsafe_allow_html=True)

# קבועים
MASTER_ADMIN = "kaliyoav@gmail.com"
SHEET_TRANSACTIONS = "Transactions"
SHEET_SETTINGS = "Settings"
SHEET_ADMINS = "Admins"
SHEET_INVENTORY = "Inventory"

# -----------------------------------------------------------------------------
# 2. AUTHENTICATION (גרסה חסינת טעויות)
# -----------------------------------------------------------------------------
authenticator = Authenticate(
    client_id=st.secrets['google_auth']['client_id'],
    client_secret=st.secrets['google_auth']['client_secret'],
    redirect_uri=st.secrets['google_auth']['redirect_uri'],
    cookie_name='soda_cookie',
    cookie_key=st.secrets['google_auth']['cookie_key'],
    cookie_expiry_days=30
)

# בדיקה אם המשתמש מחובר (מריץ לוגין אם לא)
authenticator.check_authenticity()

if not st.session_state.get('connected'):
    st.title("🥤 אפליקציית הסודה")
    st.write("נא להתחבר עם גוגל:")
    authenticator.login()
    st.stop()

# פרטי משתמש
user_info = st.session_state.get('user_info', {})
user_email = user_info.get('email')
user_name = user_info.get('name', 'משתמש')

# -----------------------------------------------------------------------------
# 3. DATABASE HELPERS
# -----------------------------------------------------------------------------
def get_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def fetch_data(worksheet_name, required_columns):
    conn = get_connection()
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0)
        for col in required_columns:
            if col not in df.columns: df[col] = None
        return df
    except:
        return pd.DataFrame(columns=required_columns)

def append_row(worksheet_name, new_row_dict, required_columns):
    conn = get_connection()
    df = fetch_data(worksheet_name, required_columns)
    updated_df = pd.concat([df, pd.DataFrame([new_row_dict])], ignore_index=True)
    conn.update(worksheet=worksheet_name, data=updated_df)
    st.cache_data.clear()

def update_full_dataframe(worksheet_name, df):
    conn = get_connection()
    conn.update(worksheet=worksheet_name, data=df)
    st.cache_data.clear()

def get_setting(key, default_val):
    df = fetch_data(SHEET_SETTINGS, ["key", "value"])
    if not df.empty and key in df["key"].values:
        return float(df[df["key"] == key].iloc[0]["value"])
    return float(default_val)

# -----------------------------------------------------------------------------
# 4. MAIN UI
# -----------------------------------------------------------------------------
def main():
    st.title(f"שלום, {user_name}")
    
    current_price = get_setting("price_per_bottle", 5.0)

    # חישוב חוב
    df_trans = fetch_data(SHEET_TRANSACTIONS, ["email", "type", "amount", "status"])
    user_df = df_trans[df_trans["email"] == user_email]
    bottles = len(user_df[user_df["type"] == "Drink"])
    paid = pd.to_numeric(user_df[(user_df["type"] == "Payment") & (user_df["status"] == "Confirmed")]["amount"], errors='coerce').sum()
    debt = (bottles * current_price) - paid

    # תצוגה
    col1, col2 = st.columns(2)
    with col1:
        st.metric("חוב נוכחי", f"₪ {debt:.2f}")
        if st.button("🥤 לקחתי בקבוק סודה", type="primary"):
            row = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": user_email, "name": user_name, "type": "Drink", "amount": 1, "status": "Confirmed"}
            append_row(SHEET_TRANSACTIONS, row, ["timestamp", "email", "name", "type", "amount", "status"])
            st.rerun()

    with col2:
        with st.form("pay"):
            amt = st.number_input("דיווח תשלום (₪)", min_value=1.0)
            if st.form_submit_button("שלח דיווח"):
                row = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": user_email, "name": user_name, "type": "Payment", "amount": amt, "status": "Pending"}
                append_row(SHEET_TRANSACTIONS, row, ["timestamp", "email", "name", "type", "amount", "status"])
                st.success("דיווח נשלח!")

    # כפתור התנתקות בסיידבר
    if st.sidebar.button("התנתק"):
        authenticator.logout()

if __name__ == "__main__":
    main()
