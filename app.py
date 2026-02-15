import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from streamlit_google_auth import Authenticate
from datetime import datetime
import time

# -----------------------------------------------------------------------------
# 1. CONFIGURATION (חייב להופיע ראשון ופעם אחת בלבד!)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ניהול סודה",
    page_icon="🥤",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# עיצוב RTL ו-CSS
st.markdown("""
    <style>
    .stApp { direction: rtl; }
    h1, h2, h3, h4, h5, h6, p, div, span { text-align: right; }
    .stButton > button { width: 100%; border-radius: 10px; height: 3em; font-weight: bold; }
    [data-testid="stMetricValue"] { direction: ltr; text-align: right; }
    </style>
""", unsafe_allow_html=True)

# קבועים
MASTER_ADMIN = "kaliyoav@gmail.com"
SHEET_TRANSACTIONS = "Transactions"
SHEET_SETTINGS = "Settings"
SHEET_ADMINS = "Admins"
SHEET_INVENTORY = "Inventory"

# -----------------------------------------------------------------------------
# 2. DATABASE HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def get_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def fetch_data(worksheet_name, required_columns):
    conn = get_connection()
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0)
        for col in required_columns:
            if col not in df.columns:
                df[col] = None
        return df
    except Exception:
        return pd.DataFrame(columns=required_columns)

def append_row(worksheet_name, new_row_dict, required_columns):
    conn = get_connection()
    df = fetch_data(worksheet_name, required_columns)
    new_df = pd.DataFrame([new_row_dict])
    updated_df = pd.concat([df, new_df], ignore_index=True)
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

def set_setting(key, value):
    df = fetch_data(SHEET_SETTINGS, ["key", "value"])
    if key in df["key"].values:
        df.loc[df["key"] == key, "value"] = value
    else:
        new_row = {"key": key, "value": value}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    update_full_dataframe(SHEET_SETTINGS, df)

# -----------------------------------------------------------------------------
# 3. AUTHENTICATION LOGIC
# -----------------------------------------------------------------------------
authenticator = Authenticate(
    client_id=st.secrets['google_auth']['client_id'],
    client_secret=st.secrets['google_auth']['client_secret'],
    redirect_uri=st.secrets['google_auth']['redirect_uri'],
    cookie_name='soda_cookie',
    cookie_key=st.secrets['google_auth']['cookie_key']
)

authenticator.check_authenticity()

if not st.session_state.get('connected'):
    st.title("🥤 אפליקציית הסודה")
    st.write("נא להתחבר עם חשבון גוגל:")
    authenticator.login()
    st.stop()

user_info = st.session_state.get('user_info', {})
user_email = user_info.get('email')
user_name = user_info.get('name', 'משתמש')

# -----------------------------------------------------------------------------
# 4. BUSINESS LOGIC
# -----------------------------------------------------------------------------
def calculate_user_debt(user_email, current_price):
    df = fetch_data(SHEET_TRANSACTIONS, ["timestamp", "email", "type", "amount", "status"])
    user_df = df[df["email"] == user_email]
    bottles_count = len(user_df[user_df["type"] == "Drink"])
    payments_df = user_df[(user_df["type"] == "Payment") & (user_df["status"] == "Confirmed")]
    total_paid = pd.to_numeric(payments_df["amount"], errors='coerce').sum()
    return (bottles_count * current_price) - total_paid

def is_admin(email):
    if email == MASTER_ADMIN: return True
    df = fetch_data(SHEET_ADMINS, ["email"])
    return email in df["email"].values

# -----------------------------------------------------------------------------
# 5. MAIN UI
# -----------------------------------------------------------------------------
def main():
    st.title("🥤 מועדון הסודה")
    
    with st.sidebar:
        if user_info.get('picture'):
            st.image(user_info['picture'], width=50)
        st.write(f"שלום, {user_name}")
        if st.button("התנתק"):
            authenticator.logout()

    current_price = get_setting("price_per_bottle", 5.0)

    # USER VIEW
    st.header(f"שלום, {user_name}")
    debt = calculate_user_debt(user_email, current_price)
    
    col_metric, col_action = st.columns([1, 2])
    with col_metric:
        st.metric(label="חוב נוכחי", value=f"₪ {debt:,.2f}")
        if debt > 0: st.warning("נא להסדיר חוב")
        else: st.success("אין חובות!")

    with col_action:
        st.subheader("פעולות מהירות")
        if st.button("🥤 לקחתי בקבוק סודה", type="primary"):
            row = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": user_email, "name": user_name, "type": "Drink", "amount": 1, "status": "Confirmed"}
            append_row(SHEET_TRANSACTIONS, row, ["timestamp", "email", "name", "type", "amount", "status"])
            st.toast("לרוויה!", icon="✅")
            time.sleep(1)
            st.rerun()

        st.markdown("---")
        with st.form("payment_form"):
            amount_paid = st.number_input("סכום שהועבר (₪)", min_value=1.0, step=1.0)
            if st.form_submit_button("דיווחתי על תשלום"):
                row = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": user_email, "name": user_name, "type": "Payment", "amount": amount_paid, "status": "Pending"}
                append_row(SHEET_TRANSACTIONS, row, ["timestamp", "email", "name", "type", "amount", "status"])
                st.success("ממתין לאישור מנהל.")
                time.sleep(1)
                st.rerun()

    # ADMIN VIEW
    if is_admin(user_email):
        st.markdown("---")
        st.error("👮 אזור ניהול")
        tab_stock, tab_payments, tab_users = st.tabs(["ניהול מלאי", "אישור תשלומים", "ניהול הרשאות"])
        
        with tab_stock:
            new_price = st.number_input("מחיר לבקבוק (₪)", value=current_price, step=0.5)
            if st.button("עדכן מחיר"):
                set_setting("price_per_bottle", new_price)
                st.rerun()
        
        with tab_payments:
            df_trans = fetch_data(SHEET_TRANSACTIONS, ["timestamp", "email", "name", "type", "amount", "status"])
            pending_df = df_trans[(df_trans["type"] == "Payment") & (df_trans["status"] == "Pending")].copy()
            if pending_df.empty:
                st.info("אין תשלומים ממתינים.")
            else:
                pending_df["Confirm"] = False
                edited_df = st.data_editor(pending_df[["timestamp", "name", "amount", "Confirm"]], key="editor")
                if st.button("אשר מסומנים"):
                    indices = edited_df[edited_df["Confirm"] == True].index
                    df_trans.loc[indices, "status"] = "Confirmed"
                    update_full_dataframe(SHEET_TRANSACTIONS, df_trans)
                    st.rerun()

if __name__ == "__main__":
    main()
