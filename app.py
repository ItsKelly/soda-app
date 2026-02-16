import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import extra_streamlit_components as stx

# --- 1. הגדרות עמוד ועיצוב בעל ניגודיות גבוהה ---
st.set_page_config(page_title="SodaClub Premium", layout="centered", page_icon="🥤")

st.markdown("""
    <style>
    /* רקע האפליקציה - אפור כהה יותר כדי להבליט אלמנטים */
    .stApp { 
        direction: rtl; 
        text-align: right; 
        background-color: #E9ECEF; 
    }
    
    /* כרטיסי המידע (Metrics) - לבן בוהק עם מסגרת כהה */
    div[data-testid="stMetric"] {
        background-color: white !important;
        padding: 20px !important;
        border-radius: 15px !important;
        box-shadow: 0 8px 16px rgba(0,0,0,0.1) !important;
        border: 2px solid #DEE2E6 !important;
    }
    
    /* כותרות המטריקות - צבע חזק */
    [data-testid="stMetricLabel"] {
        color: #495057 !important;
        font-weight: bold !important;
        font-size: 1.1rem !important;
    }

    /* כפתור "קנה סודה" - כחול עמוק וברור */
    .stButton>button[kind="primary"] {
        background-color: #0056b3 !important;
        color: white !important;
        border: none !important;
        padding: 15px !important;
        font-size: 22px !important;
        font-weight: 900 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 0 #003d7a !important; /* אפקט תלת מימד */
    }
    
    /* כפתור התנתקות ופעולות משניות - אפור כהה */
    .stButton>button[kind="secondary"] {
        background-color: #6C757D !important;
        color: white !important;
        border-radius: 10px !important;
    }

    /* תיבות בחירה וקלט - מסגרת ברורה */
    .stSelectbox, .stTextInput, .stNumberInput {
        background-color: white !important;
        border-radius: 10px !important;
        border: 2px solid #CED4DA !important;
    }
    
    /* עיצוב טאבים - ברור ומופרד */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #DEE2E6;
        border-radius: 12px 12px 0 0;
        padding: 5px;
    }
    .stTabs [data-baseweb="tab"] {
        font-weight: bold !important;
        color: #495057 !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: white !important;
        border-radius: 8px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ניהול נתונים ---
cookie_manager = stx.CookieManager()
conn = st.connection("gsheets", type=GSheetsConnection)

def get_all_data():
    u_cols = ['name', 'pin', 'role']
    t_cols = ['timestamp', 'name', 'type', 'amount', 'status', 'notes']
    try:
        u_df = conn.read(worksheet="Users", ttl=600).fillna("")
        t_df = conn.read(worksheet="Transactions", ttl=600).fillna("")
        s_df = conn.read(worksheet="Settings", ttl=600).fillna("")
        i_df = conn.read(worksheet="Inventory", ttl=600).fillna(0)
        
        for df, cols in [(u_df, u_cols), (t_df, t_cols)]:
            for col in cols:
                if col not in df.columns: df[col] = ""
        
        if not u_df.empty:
            u_df['name'] = u_df['name'].astype(str).str.strip()
            u_df['pin'] = u_df['pin'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        
        price = 2.5
        if not s_df.empty and 'key' in s_df.columns:
            p_row = s_df[s_df['key'] == 'bottle_price']
            if not p_row.empty: price = float(p_row['value'].values[0])
            
        return u_df, t_df, price, i_df
    except:
        return pd.DataFrame(columns=u_cols), pd.DataFrame(columns=t_cols), 2.5, pd.DataFrame()

users_df, trans_df, bottle_price, inv_df = get_all_data()

# --- 3. התחברות ---
if "logout_in_progress" not in st.session_state:
    st.session_state.logout_in_progress = False

if "user" not in st.session_state and not st.session_state.logout_in_progress:
    saved_name = cookie_manager.get(cookie="soda_user_name")
    if saved_name and not users_df.empty:
        user_match = users_df[users_df["name"] == saved_name]
        if not user_match.empty:
            st.session_state.user = user_match.iloc[0].to_dict()
            st.rerun()

def safe_update(ws, data):
    try:
        conn.update(worksheet=ws, data=data)
        st.cache_data.clear()
        return True
    except:
        st.error("שגיאת גוגל: נסה שוב בעוד דקה.")
        return False

# --- 4. ממשק משתמש ---
if "user" not in st.session_state:
    st.markdown("<h1 style='text-align: center; color: #0056b3;'>🥤 מועדון סודה</h1>", unsafe_allow_html=True)
    with st.container():
        st.write("---")
        u_list = users_df["name"].tolist() if not users_df.empty else []
        login_name = st.selectbox("בחר שם מהרשימה", u_list, index=None, placeholder="לחץ כאן לבחירה...")
        login_pin = st.text_input("הכנס קוד אישי", type="password")
        if st.button("כניסה למערכת", use_container_width=True, type="primary"):
            if login_name:
                u_match = users_df[users_df["name"] == login_name]
                if not u_match.empty and str(login_pin).strip() == u_match.iloc[0]["pin"]:
                    st.session_state.user = u_match.iloc[0].to_dict()
                    st.session_state.logout_in_progress = False
                    cookie_manager.set("soda_user_name", login_name, expires_at=datetime.now().replace(year=datetime.now().year + 1))
                    st.cache_data.clear()
                    st.rerun()
                else: st.error("קוד שגוי!")

else:
    curr_user = st.session_state.user
    is_admin = curr_user.get('role') == 'admin'
    tabs = st.tabs(["👤 החשבון שלי", "⚙️ ניהול"]) if is_admin else [st.container()]

    with tabs[0]:
        st.markdown(f"### אהלן, {curr_user['name']}!")
        
        # חישוב יתרה
        u_t = trans_df[trans_df["name"] == curr_user["name"]] if not trans_df.empty else pd.DataFrame()
        p_sum = u_t[u_t["type"] == "purchase"]["amount"].sum()
        pay_sum = u_t[(u_t["type"] == "payment") & (u_t["status"] == "completed")]["amount"].sum()
        adj_sum = u_t[u_t["type"] == "adjustment"]["amount"].sum()
        pend_sum = u_t[(u_t["type"] == "payment") & (u_t["status"] == "pending")]["amount"].sum()
        
        current_debt = p_sum + adj_sum - pay_sum
        
        c1, c2, c3 = st.columns(3)
        c1.metric("חוב", f"₪{current_debt:.2f}")
        c2.metric("מחיר סודה", f"₪{bottle_price}")
        if pend_sum > 0: c3.warning(f"באישור: ₪{pend_sum}")

        st.markdown("<br>", unsafe_allow_html=True)
        
        # אזור קנייה עם ניגודיות גבוהה
        with st.container():
            st.write("### ביצוע רכישה")
            col_q1, col_q2 = st.columns([1, 2])
            buy_qty = col_q1.number_input("כמות בקבוקים", min_value=1, value=1, step=1)
            if col_q2.button(f"🥤 קנה {buy_qty} ב-₪{buy_qty*bottle_price:.2f}", type="primary", use_container_width=True):
                new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": curr_user["name"], "type": "purchase", "amount": buy_qty*bottle_price, "status": "completed"}])
                if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()

        st.write("---")
        with st.expander("💳 הפקדת כסף לחשבון"):
            with st.form("pay_form"):
                amt = st.number_input("סכום (₪)", min_value=1, value=20)
                if st.form_submit_button("שלח דיווח"):
                    new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": curr_user["name"], "type": "payment", "amount": amt, "status": "pending"}])
                    if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()

        if st.button("🚪 התנתקות", type="secondary"):
            cookie_manager.delete("soda_user_name")
            st.session_state.logout_in_progress = True
            if "user" in st.session_state: del st.session_state.user
            st.cache_data.clear()
            st.rerun()

    if is_admin:
        with tabs[1]:
            st.subheader("🛠️ ניהול")
            
            # הפקדות
            pend_df = trans_df[trans_df["status"] == "pending"]
            if not pend_df.empty:
                st.info(f"ממתינים לאישור: {len(pend_df)}")
                for idx, row in pend_df.iterrows():
                    ca, cb = st.columns([3, 1])
                    ca.write(f"**{row['name']}**: ₪{row['amount']}")
                    if cb.button("אשר", key=f"ap_{idx}"):
                        trans_df.at[idx, "status"] = "completed"
                        if safe_update("Transactions", trans_df): st.rerun()
            
            st.divider()
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                stock = inv_df['quantity'].sum() - len(trans_df[trans_df['type'] == 'purchase'])
                st.metric("מלאי במקרר", int(stock))
                with st.popover("עדכון מלאי (+/-)"):
                    qc = st.number_input("שינוי", value=0)
                    if st.button("עדכן"):
                        new_i = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "quantity": qc}])
                        if safe_update("Inventory", pd.concat([inv_df, new_i], ignore_index=True)): st.rerun()
            
            with col_a2:
                st.write(f"מחיר: ₪{bottle_price}")
                with st.popover("שנה מחיר"):
                    np = st.number_input("חדש", value=bottle_price)
                    if st.button("שמור"):
                        s_new = conn.read(worksheet="Settings", ttl=0)
                        s_new.loc[s_new['key'] == 'bottle_price', 'value'] = np
                        if safe_update("Settings", s_new): st.rerun()

            st.subheader("📋 טבלת חובות")
            all_sums = []
            for _, u in users_df.iterrows():
                u_t_all = trans_df[trans_df["name"] == u["name"]]
                d = u_t_all[u_t_all["type"] == "purchase"]["amount"].sum() + u_t_all[u_t_all["type"] == "adjustment"]["amount"].sum() - u_t_all[(u_t_all["type"] == "payment") & (u_t_all["status"] == "completed")]["amount"].sum()
                all_sums.append({"שם": u["name"], "חוב": f"₪{d:.2f}"})
            st.table(pd.DataFrame(all_sums).sort_values("חוב", ascending=False))
