import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# 1. הגדרות עמוד ותמיכה בעברית (RTL)
st.set_page_config(page_title="מועדון סודה", layout="centered")
st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stForm"] { direction: rtl; }
    /* תיקון ליישור כפתורים ותיבות טקסט */
    .stButton>button { width: 100%; }
    </style>
    """, unsafe_allow_html=True)

# 2. חיבור לגיליון
conn = st.connection("gsheets", type=GSheetsConnection)

def get_cleaned_data():
    # קריאת הנתונים מהגיליון
    u_df = conn.read(worksheet="Users", ttl=0)
    t_df = conn.read(worksheet="Transactions", ttl=0)
    
    # ניקוי נתונים למניעת שגיאות התחברות
    u_df = u_df.dropna(subset=['name', 'pin']) # הסרת שורות ריקות
    u_df['name'] = u_df['name'].astype(str).str.strip()
    # הפיכת PIN לטקסט נקי (בלי .0 אם גוגל הפך אותו למספר)
    u_df['pin'] = u_df['pin'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    return u_df, t_df

# טעינת הנתונים
users_df, trans_df = get_cleaned_data()

# 3. מערכת הזדהות
if "user" not in st.session_state:
    st.header("🥤 ברוכים הבאים למועדון סודה")
    
    with st.form("login_form"):
        user_name = st.selectbox("בחר שם מהרשימה", users_df["name"].tolist())
        user_pin = st.text_input("הקש קוד אישי (4 ספרות)", type="password")
        submit = st.form_submit_button("כניסה")
        
        if submit:
            # חיפוש המשתמש בטבלה המנוקה
            user_match = users_df[users_df["name"] == user_name]
            
            if not user_match.empty:
                correct_pin = user_match.iloc[0]["pin"]
                input_pin = str(user_pin).strip()
                
                if input_pin == correct_pin:
                    st.session_state.user = user_match.iloc[0].to_dict()
                    st.success("מתחבר...")
                    st.rerun()
                else:
                    st.error("קוד שגוי, נסה שוב.")
            else:
                st.error("משתמש לא נמצא.")

else:
    # 4. ממשק משתמש מחובר (מגיע לכאן רק אחרי לוגין מוצלח)
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
        if st.button("🥤 לקחתי בקבוק (2.5 ₪)"):
            new_row = pd.DataFrame([{
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "email": user["email"],
                "type": "purchase",
                "amount": 2.5,
                "status": "completed"
            }])
            updated_df = pd.concat([trans_df, new_row], ignore_index=True)
            conn.update(worksheet="Transactions", data=updated_df)
            st.success("לרוויה!")
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
                st.info("הדיווח נשלח לאישור.")
                st.rerun()

    # היסטוריה אישית
    st.subheader("היסטוריית פעולות")
    st.dataframe(user_trans.sort_values("timestamp", ascending=False), use_container_width=True)
