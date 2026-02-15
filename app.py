import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# 1. הגדרות עמוד ותמיכה בעברית (RTL)
st.set_page_config(page_title="מועדון סודה PRO", layout="centered")
st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stForm"] { direction: rtl; }
    .stButton>button { width: 100%; }
    </style>
    """, unsafe_allow_html=True)

# 2. חיבור וטעינת נתונים
conn = st.connection("gsheets", type=GSheetsConnection)

def get_all_data():
    # טעינת כל הטאבים
    u_df = conn.read(worksheet="Users", ttl=10s).dropna(subset=['name', 'pin'])
    t_df = conn.read(worksheet="Transactions", ttl=10s).fillna("")
    s_df = conn.read(worksheet="Settings", ttl=10s)
    i_df = conn.read(worksheet="Inventory", ttl=10s).fillna(0)
    
    # ניקוי נתונים
    u_df['name'] = u_df['name'].astype(str).str.strip()
    u_df['pin'] = u_df['pin'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    # שליפת מחיר הבקבוק
    try:
        price = float(s_df[s_df['key'] == 'bottle_price']['value'].values[0])
    except:
        price = 2.5 # ברירת מחדל אם משהו השתבש
        
    return u_df, t_df, price, i_df

users_df, trans_df, bottle_price, inv_df = get_all_data()

# 3. מערכת הזדהות
if "user" not in st.session_state:
    st.header("🥤 מועדון סודה - כניסה")
    with st.form("login"):
        user_name = st.selectbox("מי אתה?", users_df["name"].tolist())
        user_pin = st.text_input("קוד אישי", type="password")
        if st.form_submit_button("התחבר"):
            user_match = users_df[users_df["name"] == user_name]
            if not user_match.empty and str(user_pin).strip() == user_match.iloc[0]["pin"]:
                st.session_state.user = user_match.iloc[0].to_dict()
                st.rerun()
            else:
                st.error("קוד שגוי")
else:
    user = st.session_state.user
    is_admin = user.get('role') == 'admin'
    
    # יצירת טאבים
    tabs = ["👤 המועדון שלי"]
    if is_admin:
        tabs.append("🛠️ ניהול מועדון")
    
    selected_tab = st.tabs(tabs)
    
    # --- טאב אישי ---
    with selected_tab[0]:
        st.title(f"שלום, {user['name']}")
        
        # לוגיקת חוב: קניות פחות תשלומים שסטטוס שלהם "completed" בלבד
        u_trans = trans_df[trans_df["email"] == user["email"]]
        total_spent = u_trans[u_trans["type"] == "purchase"]["amount"].astype(float).sum()
        total_paid = u_trans[(u_trans["type"] == "payment") & (u_trans["status"] == "completed")]["amount"].astype(float).sum()
        pending_paid = u_trans[(u_trans["type"] == "payment") & (u_trans["status"] == "pending")]["amount"].astype(float).sum()
        
        balance = total_spent - total_paid
        
        col1, col2, col3 = st.columns(3)
        col1.metric("חוב לתשלום", f"₪{balance:.2f}")
        col2.metric("מחיר בקבוק", f"₪{bottle_price}")
        if pending_paid > 0:
            col3.warning(f"ממתין לאישור: ₪{pending_paid}")

        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            if st.button(f"🥤 לקחתי בקבוק"):
                new_row = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": user["email"], "type": "purchase", "amount": bottle_price, "status": "completed"}])
                conn.update(worksheet="Transactions", data=pd.concat([trans_df, new_row], ignore_index=True))
                st.success("לרוויה!")
                st.rerun()
        
        with c2:
            with st.popover("💰 דיווחתי על תשלום"):
                amt = st.number_input("כמה שילמת?", min_value=1.0, step=1.0)
                if st.button("שלח דיווח"):
                    new_row = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": user["email"], "type": "payment", "amount": amt, "status": "pending"}])
                    conn.update(worksheet="Transactions", data=pd.concat([trans_df, new_row], ignore_index=True))
                    st.info("הדיווח נשלח לאישור מנהל. החוב יתעדכן לאחר האישור.")
                    st.rerun()

        if st.button("🚪 התנתק"):
            del st.session_state.user
            st.rerun()

    # --- טאב מנהל ---
    if is_admin:
        with selected_tab[1]:
            st.header("ניהול")
            
            # א. ניהול מלאי ומחיר
            m1, m2 = st.columns(2)
            with m1:
                st.subheader("עדכון מחיר")
                new_price = st.number_input("מחיר בקבוק חדש", value=bottle_price, step=0.5)
                if st.button("עדכן מחיר"):
                    s_df = conn.read(worksheet="Settings", ttl=0)
                    s_df.loc[s_df['key'] == 'bottle_price', 'value'] = new_price
                    conn.update(worksheet="Settings", data=s_df)
                    st.success("המחיר עודכן!")
                    st.rerun()
            
            with m2:
                st.subheader("מלאי")
                total_stock = inv_df['quantity'].sum()
                bottles_taken = len(trans_df[trans_df['type'] == 'purchase'])
                current_stock = total_stock - bottles_taken
                st.metric("בקבוקים במקרר", int(current_stock))
                
                with st.popover("➕ הוספת מלאי"):
                    q = st.number_input("כמה בקבוקים הבאת?", min_value=1, value=24)
                    if st.button("עדכן מלאי"):
                        new_inv = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "quantity": q}])
                        conn.update(worksheet="Inventory", data=pd.concat([inv_df, new_inv], ignore_index=True))
                        st.success("המלאי עודכן!")
                        st.rerun()

            st.divider()

            # ב. אישור תשלומים (החלק הקריטי)
            st.subheader("💳 תשלומים הממתינים לאישור")
            pending = trans_df[trans_df["status"] == "pending"]
            if not pending.empty:
                for idx, row in pending.iterrows():
                    u_info = users_df[users_df["email"] == row["email"]].iloc[0]
                    col_p1, col_p2 = st.columns([3, 1])
                    col_p1.write(f"**{u_info['name']}** שילם **₪{row['amount']}**")
                    if col_p2.button("אשר", key=f"app_{idx}"):
                        trans_df.at[idx, "status"] = "completed"
                        conn.update(worksheet="Transactions", data=trans_df)
                        st.rerun()
            else:
                st.write("אין תשלומים שמחכים לאישור.")

