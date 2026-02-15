import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# הגדרות עמוד ותמיכה בעברית (RTL)
st.set_page_config(page_title="מועדון סודה", layout="centered")
st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stForm"] { direction: rtl; }
    </style>
    """, unsafe_allow_html=True)

# חיבור לגיליון
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data():
    users = conn.read(worksheet="Users", ttl=0)
    trans = conn.read(worksheet="Transactions", ttl=0)
    return users, trans

users_df, trans_df = get_data()

# --- מערכת הזדהות פשוטה ---
if "user" not in st.session_state:
    st.header("🥤 ברוכים הבאים למועדון סודה")
    
    with st.form("login_form"):
        user_name = st.selectbox("בחר שם מהרשימה", users_df["name"].tolist())
        user_pin = st.text_input("הקש קוד אישי (4 ספרות)", type="password")
        submit = st.form_submit_button("כניסה")
        
        if submit:
            user_row = users_df[users_df["name"] == user_name].iloc[0]
            # וודא שהשוואת ה-PIN נעשית כטקסט
            if str(user_pin) == str(user_row["pin"]):
                st.session_state.user = user_row.to_dict()
                st.rerun()
            else:
                st.error("קוד שגוי, נסה שוב.")
else:
    # --- ממשק משתמש מחובר ---
    user = st.session_state.user
    st.title(f"שלום, {user['name']} 👋")
    
    # חישוב יתרה (חוב)
    user_trans = trans_df[trans_df["email"] == user["email"]]
    purchases = user_trans[user_trans["type"] == "purchase"]["amount"].sum()
    payments = user_trans[user_trans["type"] == "payment"]["amount"].sum()
    balance = purchases - payments
    
    col1, col2 = st.columns(2)
    col1.metric("החוב הנוכחי שלך", f"₪{balance:.2f}")
    
    if st.button("🚪 התנתק"):
        del st.session_state.user
        st.rerun()

    st.divider()

    # --- פעולות ---
    st.subheader("מה תרצה לעשות?")
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        if st.button("🥤 לקחתי בקבוק (2.5 ₪)", use_container_width=True):
            new_row = pd.DataFrame([{
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "email": user["email"],
                "type": "purchase",
                "amount": 2.5,
                "status": "completed"
            }])
            updated_df = pd.concat([trans_df, new_row], ignore_index=True)
            conn.update(worksheet="Transactions", data=updated_df)
            st.success("לרוויה! הרישום בוצע.")
            st.rerun()

    with col_b:
        with st.popover("💰 דיווח על תשלום"):
            amount = st.number_input("סכום ששולם", min_value=1, step=1)
            if st.button("שלח דיווח"):
                new_row = pd.DataFrame([{
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "email": user["email"],
                    "type": "payment",
                    "amount": amount,
                    "status": "pending"
                }])
                updated_df = pd.concat([trans_df, new_row], ignore_index=True)
                conn.update(worksheet="Transactions", data=updated_df)
                st.info("הדיווח נשלח וממתין לאישור.")
                st.rerun()

    # --- היסטוריה אישית ---
    st.subheader("היסטוריית פעולות")
    st.dataframe(user_trans.sort_values("timestamp", ascending=False), use_container_width=True)
