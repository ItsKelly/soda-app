import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# 1. הגדרות עמוד ותמיכה בעברית (RTL)
st.set_page_config(page_title="ניהול מועדון סודה", layout="centered")
st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stForm"] { direction: rtl; }
    .stButton>button { width: 100%; }
    [data-testid="stMetricValue"] { font-size: 25px; }
    </style>
    """, unsafe_allow_html=True)

# 2. חיבור לגיליון
conn = st.connection("gsheets", type=GSheetsConnection)

def get_cleaned_data():
    u_df = conn.read(worksheet="Users", ttl=0)
    t_df = conn.read(worksheet="Transactions", ttl=0)
    u_df = u_df.dropna(subset=['name', 'pin'])
    u_df['name'] = u_df['name'].astype(str).str.strip()
    u_df['pin'] = u_df['pin'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    return u_df, t_df

users_df, trans_df = get_cleaned_data()

# 3. מערכת הזדהות
if "user" not in st.session_state:
    st.header("🥤 ברוכים הבאים למועדון סודה")
    with st.form("login_form"):
        user_name = st.selectbox("בחר שם מהרשימה", users_df["name"].tolist())
        user_pin = st.text_input("הקש קוד אישי (4 ספרות)", type="password")
        submit = st.form_submit_button("כניסה")
        if submit:
            user_match = users_df[users_df["name"] == user_name]
            if not user_match.empty and str(user_pin).strip() == user_match.iloc[0]["pin"]:
                st.session_state.user = user_match.iloc[0].to_dict()
                st.rerun()
            else:
                st.error("פרטים שגויים.")
else:
    user = st.session_state.user
    
    # יצירת טאבים - רק למנהל תוצג לשונית הניהול
    if user.get('role') == 'admin':
        tab_personal, tab_admin = st.tabs(["👤 המועדון שלי", "🛠️ ניהול (מנהל בלבד)"])
    else:
        tab_personal = st.container()
        tab_admin = None

    # --- לשונית אישית ---
    with tab_personal:
        st.title(f"שלום, {user['name']}")
        
        # חישוב יתרה
        u_trans = trans_df[trans_df["email"] == user["email"]]
        purchases = u_trans[u_trans["type"] == "purchase"]["amount"].sum()
        payments = u_trans[u_trans["type"] == "payment"]["amount"].sum()
        balance = purchases - payments
        
        col1, col2 = st.columns(2)
        col1.metric("חוב נוכחי", f"₪{balance:.2f}")
        if col2.button("🚪 התנתק"):
            del st.session_state.user
            st.rerun()

        st.divider()
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🥤 לקחתי בקבוק (2.5 ₪)"):
                new_data = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": user["email"], "type": "purchase", "amount": 2.5, "status": "completed"}])
                conn.update(worksheet="Transactions", data=pd.concat([trans_df, new_data], ignore_index=True))
                st.success("נרשם!")
                st.rerun()
        with c2:
            with st.popover("💰 דיווח תשלום"):
                amt = st.number_input("סכום ששולם", min_value=1, step=1)
                if st.button("שלח"):
                    new_data = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": user["email"], "type": "payment", "amount": amt, "status": "pending"}])
                    conn.update(worksheet="Transactions", data=pd.concat([trans_df, new_data], ignore_index=True))
                    st.info("ממתין לאישור מנהל.")
                    st.rerun()

        st.subheader("היסטוריה")
        st.dataframe(u_trans.sort_values("timestamp", ascending=False), use_container_width=True)

    # --- לשונית מנהל ---
    if tab_admin:
        with tab_admin:
            st.header("ממשק מנהל")
            
            # א. סטטיסטיקה כללית
            total_debt = 0
            pending_payments = trans_df[trans_df["status"] == "pending"]
            
            # חישוב חובות של כולם
            all_balances = []
            for _, u in users_df.iterrows():
                ut = trans_df[trans_df["email"] == u["email"]]
                bal = ut[ut["type"] == "purchase"]["amount"].sum() - ut[ut["type"] == "payment"]["amount"].sum()
                all_balances.append({"שם": u["name"], "חוב": bal})
                total_debt += bal

            col_a, col_b = st.columns(2)
            col_a.metric("סה\"כ חובות במועדון", f"₪{total_debt:.2f}")
            col_b.metric("תשלומים לאישור", len(pending_payments))

            # ב. אישור תשלומים
            st.subheader("תשלומים הממתינים לאישור")
            if not pending_payments.empty:
                for idx, row in pending_payments.iterrows():
                    # מציאת שם המשתמש לפי האימייל
                    u_name = users_df[users_df["email"] == row["email"]]["name"].iloc[0]
                    with st.expander(f"{u_name} - {row['amount']} ₪ ({row['timestamp']})"):
                        if st.button(f"אשר תשלום של {u_name}", key=f"btn_{idx}"):
                            # עדכון הסטטוס ב-Dataframe
                            trans_df.at[idx, "status"] = "completed"
                            conn.update(worksheet="Transactions", data=trans_df)
                            st.success("עודכן!")
                            st.rerun()
            else:
                st.write("אין תשלומים שמחכים לאישור.")

            # ג. טבלת חובות כללית
            st.subheader("מצב חובות כללי")
            st.table(pd.DataFrame(all_balances).sort_values("חוב", ascending=False))
