import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# הגדרות דף
st.set_page_config(page_title="מועדון הסודה", layout="centered")
st.markdown("<style>.stApp { direction: rtl; text-align: right; }</style>", unsafe_allow_html=True)

# חיבור לגיליון
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data(sheet):
    return conn.read(worksheet=sheet, ttl=0)

# 1. מסך כניסה (Login פשוט עם PIN)
st.title("🥤 מועדון הסודה המשרדי")

users_df = get_data("Users")
user_names = users_df["name"].tolist()

selected_name = st.selectbox("מי אתה?", ["בחר שם..."] + user_names)

if selected_name != "בחר שם...":
    user_row = users_df[users_df["name"] == selected_name].iloc[0]
    user_pin = str(user_row["pin"])
    user_email = user_row["email"]
    
    input_pin = st.text_input("הכנס קוד אישי (PIN)", type="password")
    
    if input_pin == user_pin:
        st.success(f"שלום {selected_name}, זוהית בהצלחה!")
        
        # --- כאן מגיע התוכן של האפליקציה ---
        
        # שליפת מחיר מהגדרות
        settings_df = get_data("Settings")
        price = float(settings_df[settings_df["key"] == "price_per_bottle"].iloc[0]["value"])
        
        # חישוב חוב (ספירת שורות ב-Transactions)
        trans_df = get_data("Transactions")
        user_trans = trans_df[trans_df["email"] == user_email]
        drinks = len(user_trans[user_trans["type"] == "Drink"])
        paid = pd.to_numeric(user_trans[(user_trans["type"] == "Payment") & (user_trans["status"] == "Confirmed")]["amount"], errors='coerce').sum()
        debt = (drinks * price) - paid
        
        st.metric("החוב שלך", f"₪ {debt:.2f}")
        
        if st.button("🥤 לקחתי בקבוק סודה", type="primary"):
            new_row = pd.DataFrame([{
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "email": user_email,
                "name": selected_name,
                "type": "Drink",
                "amount": 1,
                "status": "Confirmed"
            }])
            updated_df = pd.concat([trans_df, new_row], ignore_index=True)
            conn.update(worksheet="Transactions", data=updated_df)
            st.balloons()
            st.toast("נרשם בהצלחה!")
            st.rerun()
            
    elif input_pin != "":
        st.error("קוד שגוי, נסה שוב.")
