import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import extra_streamlit_components as stx

# --- 1. הגדרות עמוד ועיצוב (RTL + Alignment) ---
st.set_page_config(page_title="מועדון סודה", layout="centered", page_icon="🥤")

st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stForm"] { direction: rtl; }
    .stTabs [data-baseweb="tab-list"] { direction: rtl; justify-content: center; }
    /* מרכז כותרות וטקסט מסוים */
    .centered-text { text-align: center; width: 100%; }
    .balance-box {
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        font-size: 24px;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ניהול עוגיות וחיבור נתונים ---
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
        
        price = 2.5
        if not s_df.empty and 'key' in s_df.columns:
            p_row = s_df[s_df['key'] == 'bottle_price']
            if not p_row.empty: price = float(p_row['value'].values[0])
            
        return u_df, t_df, price, i_df
    except:
        return pd.DataFrame(columns=u_cols), pd.DataFrame(columns=t_cols), 2.5, pd.DataFrame()

users_df, trans_df, bottle_price, inv_df = get_all_data()

# --- 3. לוגיקת יתרה ועדכון ---
def calculate_balance(name, df):
    if df.empty or name not in df['name'].values: return 0.0, 0.0
    u_t = df[df["name"] == name]
    purchases = u_t[u_t["type"] == "purchase"]["amount"].sum()
    payments = u_t[(u_t["type"] == "payment") & (u_t["status"] == "completed")]["amount"].sum()
    adjustments = u_t[u_t["type"] == "adjustment"]["amount"].sum()
    pending = u_t[(u_t["type"] == "payment") & (u_t["status"] == "pending")]["amount"].sum()
    # יתרה = הפקדות - (קניות + התאמות)
    return (payments - (purchases + adjustments)), pending

def safe_update(ws, data):
    try:
        conn.update(worksheet=ws, data=data)
        st.cache_data.clear()
        return True
    except:
        st.error("שגיאת גוגל. נסה שוב בעוד דקה.")
        return False

# --- 4. כניסה למערכת ---
if "logout_in_progress" not in st.session_state:
    st.session_state.logout_in_progress = False

if "user" not in st.session_state and not st.session_state.logout_in_progress:
    saved_name = cookie_manager.get(cookie="soda_user_name")
    if saved_name and not users_df.empty:
        user_match = users_df[users_df["name"] == saved_name]
        if not user_match.empty:
            st.session_state.user = user_match.iloc[0].to_dict()
            st.rerun()

if "user" not in st.session_state:
    st.markdown("<h1 class='centered-text'>🥤 מועדון סודה</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login_form"):
            u_list = users_df["name"].tolist() if not users_df.empty else []
            login_name = st.selectbox("מי אתה?", u_list, index=None, placeholder="בחר שם...")
            login_pin = st.text_input("קוד אישי", type="password")
            if st.form_submit_button("כניסה", use_container_width=True):
                if login_name:
                    u_match = users_df[users_df["name"] == login_name]
                    if not u_match.empty and str(login_pin).strip() == u_match.iloc[0]["pin"]:
                        st.session_state.user = u_match.iloc[0].to_dict()
                        st.session_state.logout_in_progress = False
                        cookie_manager.set("soda_user_name", login_name, expires_at=datetime.now().replace(year=datetime.now().year + 1))
                        st.cache_data.clear()
                        st.rerun()
                    else: st.error("קוד שגוי.")

else:
    user = st.session_state.user
    is_admin = user.get('role') == 'admin'
    tabs = st.tabs(["👤 החשבון שלי", "🛠️ ניהול"]) if is_admin else [st.container()]

    with tabs[0]:
        st.markdown(f"<h2 class='centered-text'>שלום, {user['name']}</h2>", unsafe_allow_html=True)
        
        balance, pending = calculate_balance(user['name'], trans_df)
        
        # תצוגת יתרה צבעונית ומיושרת
        color = "#28a745" if balance >= 0 else "#dc3545"
        st.markdown(f"""
            <div class="balance-box" style="color: {color}; border: 2px solid {color};">
                יתרה בחשבון: ₪{balance:.2f}
            </div>
            """, unsafe_allow_html=True)
        
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("מחיר בקבוק", f"₪{bottle_price}")
        if pending > 0: col_m2.warning(f"ממתין לאישור: ₪{pending}")

        st.divider()

        # קנייה מרובה - מיושר
        with st.expander("🥤 רכישת סודה", expanded=True):
            cq1, cq2 = st.columns([1, 2])
            qty = cq1.number_input("כמות", min_value=1, value=1)
            if cq2.button(f"אשר רכישה (₪{qty*bottle_price:.2f})", type="primary", use_container_width=True):
                new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": user["name"], "type": "purchase", "amount": qty*bottle_price, "status": "completed", "notes": ""}])
                if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()
        
        # הפקדה - מיושר
        with st.expander("💳 הפקדת כסף"):
            with st.form("pay_f", clear_on_submit=True):
                p_amt = st.number_input("סכום להפקדה (₪)", min_value=1.0, value=20.0)
                if st.form_submit_button("שלח בקשה", use_container_width=True):
                    new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": user["name"], "type": "payment", "amount": p_amt, "status": "pending", "notes": ""}])
                    if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()

        if st.button("🚪 התנתק", use_container_width=True):
            cookie_manager.delete("soda_user_name")
            st.session_state.logout_in_progress = True
            if "user" in st.session_state: del st.session_state.user
            st.cache_data.clear()
            st.rerun()

    if is_admin:
        with tabs[1]:
            st.markdown("<h2 class='centered-text'>ניהול המועדון</h2>", unsafe_allow_html=True)
            
            # אישור הפקדות
            st.subheader("💳 אישור הפקדות")
            p_df = trans_df[trans_df["status"] == "pending"]
            if not p_df.empty:
                for idx, row in p_df.iterrows():
                    ca, cb = st.columns([3, 1])
                    ca.write(f"**{row['name']}**: הפקיד ₪{row['amount']}")
                    if cb.button("אשר", key=f"ap_{idx}", use_container_width=True):
                        trans_df.at[idx, "status"] = "completed"
                        if safe_update("Transactions", trans_df): st.rerun()
            else: st.info("אין הפקדות ממתינות.")

            st.divider()

            # מלאי ומחיר - סימטרי
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("📦 מלאי")
                stock = inv_df['quantity'].sum() - len(trans_df[trans_df['type'] == 'purchase'])
                st.metric("במקרר", int(stock))
                with st.popover("עדכן מלאי", use_container_width=True):
                    qc = st.number_input("שינוי (+/-)", value=0)
                    if st.button("בצע עדכון", use_container_width=True):
                        new_i = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "quantity": qc}])
                        if safe_update("Inventory", pd.concat([inv_df, new_i], ignore_index=True)): st.rerun()
            
            with col_b:
                st.subheader("💰 הגדרות")
                st.metric("מחיר נוכחי", f"₪{bottle_price}")
                with st.popover("שנה מחיר", use_container_width=True):
                    np = st.number_input("מחיר חדש", value=bottle_price)
                    if st.button("שמור", use_container_width=True):
                        s_new = conn.read(worksheet="Settings", ttl=0)
                        s_new.loc[s_new['key'] == 'bottle_price', 'value'] = np
                        if safe_update("Settings", s_new): st.rerun()

            st.divider()

            # עדכון יתרה ידני
            with st.expander("🔄 עדכון יתרה ידני למשתמש"):
                with st.form("adj_f"):
                    t_user = st.selectbox("בחר משתמש", users_df["name"].tolist())
                    t_amt = st.number_input("סכום לשינוי (חיובי מוסיף יתרה, שלילי מוריד)", value=0.0)
                    t_note = st.text_input("סיבה")
                    # חשוב: כאן אנחנו הופכים את הסימן כי בטרנזקציות adjustment חיובי אצלנו נחשב חוב
                    if st.form_submit_button("בצע עדכון", use_container_width=True):
                        if t_amt != 0:
                            new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": t_user, "type": "adjustment", "amount": -t_amt, "status": "completed", "notes": t_note}])
                            if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()

            # טבלת יתרות - מיושרת וסימטרית
            st.subheader("📊 טבלת יתרות כללית")
            if not users_df.empty:
                sums = []
                for _, u in users_df.iterrows():
                    bal, _ = calculate_balance(u['name'], trans_df)
                    sums.append({"שם": u["name"], "יתרה (₪)": round(bal, 2)})
                st.dataframe(pd.DataFrame(sums).sort_values("יתרה (₪)", ascending=False), use_container_width=True, hide_index=True)
