import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from streamlit_google_auth import Authenticate
from datetime import datetime
import time

# -----------------------------------------------------------------------------
# 1. CONFIGURATION & STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ניהול סודה",
    page_icon="🥤",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for Hebrew RTL and UI polishing
st.markdown("""
    <style>
    /* General RTL support */
    .stApp {
        direction: rtl;
    }
    h1, h2, h3, h4, h5, h6, p, div, span {
        text-align: right;
    }
    /* Align buttons and inputs */
    .stButton > button {
        width: 100%;
        border-radius: 10px;
        height: 3em;
        font-weight: bold;
    }
    /* Metrics alignment */
    [data-testid="stMetricValue"] {
        direction: ltr; /* Numbers look better LTR usually, but aligned right */
        text-align: right;
    }
    /* Dataframe alignment */
    .stDataFrame {
        direction: ltr; /* Keep tables standard, usually easier to read */
    }
    </style>
""", unsafe_allow_html=True)

# Constants
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
        # ttl=0 ensures we don't serve stale cache on actions
        df = conn.read(worksheet=worksheet_name, ttl=0)
        # Ensure all columns exist
        for col in required_columns:
            if col not in df.columns:
                df[col] = None
        return df
    except Exception:
        # If sheet is empty or doesn't exist, return empty DF
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
    row = df[df["key"] == key]
    if not row.empty:
        return float(row.iloc[0]["value"])
    return float(default_val)

def set_setting(key, value):
    df = fetch_data(SHEET_SETTINGS, ["key", "value"])
    # Check if exists, update or append
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
    secret_credentials_path=None, # Not used if secrets are in toml
    cookie_name=st.secrets['auth']['cookie_name'],
    client_id=st.secrets['auth']['client_id'],
    client_secret=st.secrets['auth']['client_secret'],
    redirect_uri=st.secrets['auth']['redirect_uri'],
)

# -----------------------------------------------------------------------------
# 4. BUSINESS LOGIC
# -----------------------------------------------------------------------------
def calculate_user_debt(user_email, current_price):
    df = fetch_data(SHEET_TRANSACTIONS, ["timestamp", "email", "type", "amount", "status"])
    
    # Filter for user
    user_df = df[df["email"] == user_email]
    
    # 1. Total Bottles Taken
    bottles_count = len(user_df[user_df["type"] == "Drink"])
    
    # 2. Total CONFIRMED Payments
    payments_df = user_df[
        (user_df["type"] == "Payment") & 
        (user_df["status"] == "Confirmed")
    ]
    # Convert amount to numeric, coerce errors
    total_paid = pd.to_numeric(payments_df["amount"], errors='coerce').sum()
    
    # 3. Calculation
    current_debt = (bottles_count * current_price) - total_paid
    return current_debt

def is_admin(email):
    if email == MASTER_ADMIN:
        return True
    df = fetch_data(SHEET_ADMINS, ["email"])
    if email in df["email"].values:
        return True
    return False

# -----------------------------------------------------------------------------
# 5. MAIN UI
# -----------------------------------------------------------------------------
def main():
    st.title("🥤 מועדון הסודה")

    # Check Login
    authenticator.check_authentification()

    if not st.session_state.get('connected'):
        st.info("נא להתחבר באמצעות חשבון גוגל כדי להמשיך")
        authenticator.login()
        st.stop()

    # User is Logged In
    user_info = st.session_state['user_info']
    user_email = user_info['email']
    user_name = user_info.get('name', 'משתמש')

    # Sidebar Logout
    with st.sidebar:
        st.image(user_info.get('picture', ''), width=50)
        st.write(f"שלום, {user_name}")
        if st.button("התנתק"):
            authenticator.logout()

    # Fetch Global Settings
    current_price = get_setting("price_per_bottle", 5.0)

    # --- USER VIEW ---
    st.header(f"שלום, {user_name}")
    
    # 1. Display Balance
    debt = calculate_user_debt(user_email, current_price)
    
    col_metric, col_action = st.columns([1, 2])
    
    with col_metric:
        color = "normal" if debt <= 0 else "inverse"
        st.metric(label="חוב נוכחי", value=f"₪ {debt:,.2f}", delta=None)
        if debt > 0:
            st.warning("נא להסדיר חוב בהקדם")
        else:
            st.success("אין חובות! תהנה/י")

    with col_action:
        st.subheader("פעולות מהירות")
        
        # Action: Take Bottle
        if st.button("🥤 לקחתי בקבוק סודה", type="primary"):
            row = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "email": user_email,
                "name": user_name,
                "type": "Drink",
                "amount": 1,
                "status": "Confirmed" # Drink is self-confirmed
            }
            append_row(SHEET_TRANSACTIONS, row, ["timestamp", "email", "name", "type", "amount", "status"])
            st.toast("נרשם בהצלחה! לרוויה.", icon="✅")
            time.sleep(1)
            st.rerun()

        st.markdown("---")
        
        # Action: Report Payment
        st.write("דיווח על תשלום (ביט/מזומן)")
        with st.form("payment_form"):
            amount_paid = st.number_input("סכום שהועבר (₪)", min_value=1.0, step=1.0)
            submitted = st.form_submit_button("דיווחתי על העברת תשלום")
            
            if submitted:
                row = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "email": user_email,
                    "name": user_name,
                    "type": "Payment",
                    "amount": amount_paid,
                    "status": "Pending" # Needs admin approval
                }
                append_row(SHEET_TRANSACTIONS, row, ["timestamp", "email", "name", "type", "amount", "status"])
                st.success("הדיווח נשלח וממתין לאישור מנהל.")
                time.sleep(1.5)
                st.rerun()

    # --- ADMIN VIEW ---
    if is_admin(user_email):
        st.markdown("---")
        st.error("👮 אזור ניהול (Admin)")
        
        tab_stock, tab_payments, tab_users = st.tabs(["ניהול מלאי ומחיר", "אישור תשלומים", "ניהול הרשאות"])
        
        # Tab 1: Stock & Price
        with tab_stock:
            st.subheader("הגדרות מחיר")
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                new_price = st.number_input("מחיר לבקבוק (₪)", value=current_price, step=0.5)
            with col_p2:
                st.write("") # Spacer
                st.write("")
                if st.button("עדכן מחיר"):
                    set_setting("price_per_bottle", new_price)
                    st.toast("המחיר עודכן בהצלחה!")
                    time.sleep(1)
                    st.rerun()
            
            st.divider()
            st.subheader("הוספת ארגז למלאי")
            with st.form("add_crate"):
                c_cost = st.number_input("עלות הארגז (₪)", min_value=0.0)
                c_count = st.number_input("מספר בקבוקים בארגז", min_value=1, value=6)
                c_submit = st.form_submit_button("הוסף ארגז")
                
                if c_submit:
                    inv_row = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "admin_email": user_email,
                        "cost": c_cost,
                        "bottles_count": c_count
                    }
                    append_row(SHEET_INVENTORY, inv_row, ["timestamp", "admin_email", "cost", "bottles_count"])
                    st.success("הארגז נרשם במערכת.")

        # Tab 2: Payments Approval
        with tab_payments:
            st.subheader("תשלומים ממתינים לאישור")
            
            # Fetch transactions
            df_trans = fetch_data(SHEET_TRANSACTIONS, ["timestamp", "email", "name", "type", "amount", "status"])
            
            # Filter Pending Payments
            pending_mask = (df_trans["type"] == "Payment") & (df_trans["status"] == "Pending")
            pending_df = df_trans[pending_mask].copy()
            
            if pending_df.empty:
                st.info("אין תשלומים שממתינים לאישור.")
            else:
                # Add a selection column for the editor
                pending_df["Confirm"] = False
                
                # Show editable dataframe
                edited_df = st.data_editor(
                    pending_df[["timestamp", "name", "amount", "Confirm"]],
                    column_config={
                        "timestamp": "זמן",
                        "name": "שם",
                        "amount": st.column_config.NumberColumn("סכום", format="₪ %.2f"),
                        "Confirm": st.column_config.CheckboxColumn("אישור", default=False)
                    },
                    hide_index=True,
                    key="payment_editor"
                )
                
                if st.button("אשר תשלומים מסומנים"):
                    # Find which rows were checked
                    # Note: We match by timestamp/name/amount assuming uniqueness for simplicity in this context, 
                    # or strictly by index if the dataframe hasn't been resorted.
                    # A robust way is iterating the edited_df index.
                    
                    indices_to_confirm = edited_df[edited_df["Confirm"] == True].index
                    
                    if len(indices_to_confirm) > 0:
                        # Update the original dataframe using the indices from the filtered view
                        # We must map filtered indices back to original dataframe indices
                        original_indices = pending_df.index[pending_df.index.isin(indices_to_confirm)]
                        
                        df_trans.loc[original_indices, "status"] = "Confirmed"
                        update_full_dataframe(SHEET_TRANSACTIONS, df_trans)
                        st.success(f"אושרו {len(indices_to_confirm)} תשלומים.")
                        time.sleep(1)
                        st.rerun()

        # Tab 3: Manage Admins
        with tab_users:
            st.subheader("ניהול מנהלים")
            st.write(f"Master Admin: {MASTER_ADMIN}")
            
            # Show current additional admins
            admins_df = fetch_data(SHEET_ADMINS, ["email"])
            st.table(admins_df)
            
            new_admin_email = st.text_input("הכנס אימייל להוספה כמנהל")
            if st.button("הוסף מנהל"):
                if new_admin_email and "@" in new_admin_email:
                    if new_admin_email not in admins_df["email"].values:
                        append_row(SHEET_ADMINS, {"email": new_admin_email}, ["email"])
                        st.success("נוסף בהצלחה.")
                        st.rerun()
                    else:
                        st.warning("המשתמש כבר מנהל.")
                else:
                    st.warning("כתובת אימייל לא תקינה.")

if __name__ == "__main__":
    main()