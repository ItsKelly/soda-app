import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# הגדרות דף
st.set_page_config(page_title="מועדון הסודה", layout="centered")
st.markdown("<style>.stApp { direction: rtl; text-align: right; }</style>", unsafe_allow_html=True)

# חיבור לגיליון (עם טיפול בשגיאות)
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("שגיאה בחיבור לבסיס הנתונים. וודא שה-Secrets מוגדרים נכון.")
    st.stop()

def get_data(sheet_name):
    try:
        # שורה חדשה לבדיקה:
        st.write("טאבים שמצאתי בגיליון:", conn.list_worksheets()) 
        
        return conn.read(worksheet=sheet_name, ttl=0)
    except Exception as e:
        st.error(f"לא מצליח למצוא את הטאב '{sheet_name}'.")
        return pd.DataFrame()

st.title("🥤 מועדון הסודה")

# טעינת משתמשים
users_df = get_data("Users")

if not users_df.empty:
    user_names = users_df["name"].tolist()
    selected_name = st.selectbox("מי אתה?", ["בחר שם..."] + user_names)

    if selected_name != "בחר שם...":
        user_row = users_df[users_df["name"] == selected_name].iloc[0]
        user_pin = str(user_row["pin"])
        user_email = user_row["email"]
        
        input_pin = st.text_input("הכנס קוד אישי (PIN)", type="password")
        
        if input_pin == user_pin:
            st.success(f"שלום {selected_name}!")
            
            # טעינת נתונים נוספים רק אחרי התחברות
            settings_df = get_data("Settings")
            price = 5.0 # ברירת מחדל
            if not settings_df.empty:
                price_row = settings_df[settings_df["key"] == "price_per_bottle"]
                if not price_row.empty:
                    price = float(price_row.iloc[0]["value"])
            
            trans_df = get_data("Transactions")
            
            # חישוב חוב
            if not trans_df.empty:
                user_trans = trans_df[trans_df["email"] == user_email]
                drinks = len(user_trans[user_trans["type"] == "Drink"])
                paid = pd.to_numeric(user_trans[(user_trans["type"] == "Payment") & (user_trans["status"] == "Confirmed")]["amount"], errors='coerce').sum()
                debt = (drinks * price) - paid
                st.metric("חוב נוכחי", f"₪ {debt:.2f}")

            if st.button("🥤 לקחתי בקבוק סודה", type="primary"):
                # לוגיקה להוספת שורה (כפי שכתבנו קודם)
                st.toast("נרשם!")
        elif input_pin != "":
            st.error("קוד שגוי")
else:
    st.warning("טוען נתונים... וודא שיש טאב בשם 'Users' בגיליון שלך.")

