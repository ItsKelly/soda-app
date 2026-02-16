import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import extra_streamlit_components as stx

# --- 1. הגדרות עמוד ועיצוב Mobile-First ---
st.set_page_config(page_title="SodaClub Mobile", layout="centered", page_icon="🥤")

st.markdown("""
    <style>
    /* הגדרות בסיס לרשת ויישור */
    .stApp { direction: rtl; text-align: right; background-color: #ffffff; }
    
    /* הפיכת כל הכפתורים לגדולים ונוחים למגע */
    .stButton > button {
        width: 100% !important;
        height: 55px !important;
        font-size: 18px !important;
        border-radius: 12px !important;
        font-weight: bold !important;
        margin-bottom: 10px !important;
    }
    
    /* תיבת היתרה - עיצוב כרטיס מובייל */
    .balance-card {
        padding: 25px;
        border-radius: 18px;
        text-align: center;
        margin-bottom: 25px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .balance-label { font-size: 16px; opacity: 0.8; margin-bottom: 5px; }
    .balance-value { font-size: 32px; font-weight: 800; }

    /* תיבות קלט גבוהות יותר */
    .stSelectbox, .stTextInput, .stNumberInput {
        margin-bottom: 15px !important;
    }
    div[data-baseweb="select"] > div {
        height: 50px !important;
        border-radius: 10px !important;
    }

    /* כותרות מיושרות למרכז */
    .centered-title {
        text-align: center;
        padding: 20px 0;
        color: #1f2937;
    }
    
    /* עיצוב טאבים מותאם למובייל */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        justify-content: center;
    }
    .stTabs [data-baseweb="tab"] {
        height: 45px !important;
        border-radius: 10px 10px 0 0 !important;
        font-weight: 600 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ניהול נתונים ---
cookie_manager = stx.CookieManager()
conn = st.connection("gsheets", type=GSheetsConnection)

def get_all_data():
    u_cols, t_cols = ['name', 'pin', 'role'], ['timestamp', 'name', 'type', 'amount', 'status', 'notes']
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
            
        return u_df, t_df, s_df, i_df
    except:
        return pd.DataFrame(columns=u_cols), pd.DataFrame(columns=t_cols), pd.DataFrame(), pd.DataFrame()

users_df, trans_df, settings_df, inv_df = get_all_data()

# שליפת מחיר
bottle_price = 2.5
if not settings_df.empty and 'key' in settings_df.columns:
    p_row = settings_df[settings_df['key'] == 'bottle_price']
    if not p_row.empty: bottle_price = float(p_row['value'].values[0])

# --- 3. לוגיקה ---
def calculate_balance(name, df):
    if df.empty or name not in df['name'].values: return 0.0, 0.0
    u_t = df[df["name"] == name]
    purchases = u_t[u_t["type"] == "purchase"]["amount"].sum()
    payments = u_t[(u_t["type"] == "payment") & (u_t["status"] == "completed")]["amount"].sum()
    adjustments = u_t[u_t["type"] == "adjustment"]["amount"].sum()
    pending = u_t[(u_t["type"] == "payment") & (u_t["status"] == "pending")]["amount"].sum()
    return (payments - (purchases + adjustments)), pending

def safe_update(ws, data):
    try:
        conn.update(worksheet=ws, data=data)
        st.cache_data.clear()
        return True
    except:
        st.error("שגיאת גוגל. נסה שוב בעוד דקה.")
        return False

# --- 4. כניסה / יציאה ---
if "logout_in_progress" not in st.session_state:
    st.session_state.logout_in_progress = False

if "user" not in st.session_state and not st.session_state.logout_in_progress:
    saved_name = cookie_manager.get(cookie="soda_user_name")
    if saved_name and not users_df.empty:
        u_match = users_df[users_df["name"] == saved_name]
        if not u_match.empty:
            st.session_state.user = u_match.iloc[0].to_dict()
            st.rerun()

# --- 5. ממשק המשתמש ---
if "user" not in st.session_state:
    st.markdown("<h1 class='centered-title'>🥤 מועדון סודה</h1>", unsafe_allow_html=True)
    col_l1, col_l2, col_l3 = st.columns([0.1, 0.8, 0.1])
    with col_l2:
        with st.form("login_form"):
            u_list = users_df["name"].tolist() if not users_df.empty else []
            login_name = st.selectbox("מי מגיע לשתות?", u_list, index=None, placeholder="בחר שם מהרשימה...")
            login_pin = st.text_input("קוד אישי", type="password")
            if st.form_submit_button("כניסה למערכת"):
                if login_name:
                    u_m = users_df[users_df["name"] == login_name]
                    if not u_m.empty and str(login_pin).strip() == u_m.iloc[0]["pin"]:
                        st.session_state.user = u_m.iloc[0].to_dict()
                        st.session_state.logout_in_progress = False
                        cookie_manager.set("soda_user_name", login_name, expires_at=datetime.now().replace(year=datetime.now().year + 1))
                        st.cache_data.clear()
                        st.rerun()
                    else: st.error("קוד שגוי")

else:
    user = st.session_state.user
    is_admin = user.get('role') == 'admin'
    
    # טאבים עם זיכרון
    tabs = st.tabs(["👤 החשבון שלי", "🛠️ ניהול"]) if is_admin else [st.container()]

    with tabs[0]:
        st.markdown(f"<h2 class='centered-title'>היי, {user['name']}</h2>", unsafe_allow_html=True)
        
        balance, pending = calculate_balance(user['name'], trans_df)
        bg_color = "#e6fffa" if balance >= 0 else "#fff5f5"
        text_color = "#2c7a7b" if balance >= 0 else "#c53030"
        border_color = "#81e6d9" if balance >= 0 else "#feb2b2"
        
        st.markdown(f"""
            <div class="balance-card" style="background-color: {bg_color}; border: 1px solid {border_color};">
                <div class="balance-label" style="color: {text_color};">יתרה בחשבון</div>
                <div class="balance-value" style="color: {text_color};">₪{balance:.2f}</div>
            </div>
            """, unsafe_allow_html=True)
        
        c_m1, c_m2 = st.columns(2)
        c_m1.metric("מחיר סודה", f"₪{bottle_price}")
        if pending > 0: c_m2.warning(f"ממתין לאישור: ₪{pending}")

        st.divider()

        # קנייה - כפתור ענק
        st.write("### 🥤 רכישה מהירה")
        cq1, cq2 = st.columns([1, 2])
        qty = cq1.number_input("כמות", min_value=1, value=1, step=1)
        if cq2.button(f"אשר קנייה (₪{qty*bottle_price:.2f})", type="primary"):
            new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": user["name"], "type": "purchase", "amount": qty*bottle_price, "status": "completed", "notes": ""}])
            if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()
        
        st.write("### 💳 טעינת כסף")
        with st.expander("לחץ כאן לדיווח על הפקדה"):
            with st.form("pay_f", clear_on_submit=True):
                p_amt = st.number_input("סכום בשקלים", min_value=1.0, value=20.0, step=1.0)
                if st.form_submit_button("שלח בקשה"):
                    new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": user["name"], "type": "payment", "amount": p_amt, "status": "pending", "notes": ""}])
                    if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()

        st.divider()
        if st.button("🚪 התנתקות מהמכשיר"):
            cookie_manager.delete("soda_user_name")
            st.session_state.logout_in_progress = True
            if "user" in st.session_state: del st.session_state.user
            st.cache_data.clear()
            st.rerun()

    if is_admin:
        with tabs[1]:
            st.markdown("<h2 class='centered-title'>ניהול מערכת</h2>", unsafe_allow_html=True)
            
            # אישור הפקדות
            p_df = trans_df[trans_df["status"] == "pending"]
            if not p_df.empty:
                st.subheader("אישור הפקדות")
                for idx, row in p_df.iterrows():
                    ca, cb = st.columns([2, 1])
                    ca.write(f"**{row['name']}**: ₪{row['amount']}")
                    if cb.button("אשר ✅", key=f"ap_{idx}"):
                        trans_df.at[idx, "status"] = "completed"
                        if safe_update("Transactions", trans_df): st.rerun()
            else: st.info("אין הפקדות ממתינות")

            st.divider()

            # מלאי ומחיר
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**📦 מלאי**")
                stock = inv_df['quantity'].sum() - len(trans_df[trans_df['type'] == 'purchase'])
                st.metric("במקרר", int(stock))
                with st.popover("עדכן", use_container_width=True):
                    qc = st.number_input("שינוי (+/-)", value=0, step=1)
                    if st.button("בצע"):
                        new_i = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "quantity": qc}])
                        if safe_update("Inventory", pd.concat([inv_df, new_i], ignore_index=True)): st.rerun()
            
            with col_b:
                st.write("**💰 מחיר**")
                st.metric("נוכחי", f"₪{bottle_price}")
                with st.popover("שנה", use_container_width=True):
                    np = st.number_input("חדש", value=bottle_price, step=0.5)
                    if st.button("שמור"):
                        s_new = conn.read(worksheet="Settings", ttl=0)
                        s_new.loc[s_new['key'] == 'bottle_price', 'value'] = np
                        if safe_update("Settings", s_new): st.rerun()

            st.divider()
            
            # עדכון יתרה ידני
            with st.expander("🔄 עדכון יתרה ידני"):
                with st.form("adj_f"):
                    t_user = st.selectbox("בחר משתמש", users_df["name"].tolist())
                    t_amt = st.number_input("סכום (חיובי = הוספת כסף)", value=0.0, step=1.0)
                    t_note = st.text_input("סיבה")
                    if st.form_submit_button("בצע"):
                        if t_amt != 0:
                            new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": t_user, "type": "adjustment", "amount": -t_amt, "status": "completed", "notes": t_note}])
                            if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()

            st.subheader("טבלת יתרות")
            if not users_df.empty:
                sums = []
                for _, u in users_df.iterrows():
                    bal, _ = calculate_balance(u['name'], trans_df)
                    sums.append({"שם": u["name"], "יתרה": round(bal, 2)})
                st.dataframe(pd.DataFrame(sums).sort_values("יתרה", ascending=False), use_container_width=True, hide_index=True)
