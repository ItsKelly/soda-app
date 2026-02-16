import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import extra_streamlit_components as stx

# --- 1. הגדרות עמוד ויישור לימין (RTL) בלבד ---
st.set_page_config(page_title="מועדון סודה", layout="centered", page_icon="🥤")

st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stForm"] { direction: rtl; }
    .stTabs [data-baseweb="tab-list"] { direction: rtl; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ניהול עוגיות וחיבור נתונים ---
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

# --- 3. לוגיקת התחברות ---
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
        st.error("שגיאת עדכון: גוגל חסם את הבקשה זמנית. נסה שוב בעוד דקה.")
        return False

# --- 4. ממשק משתמש ---
if "user" not in st.session_state:
    st.title("🥤 מועדון סודה")
    with st.form("login_form"):
        u_list = users_df["name"].tolist() if not users_df.empty else []
        login_name = st.selectbox("בחר שם מהרשימה", u_list, index=None, placeholder="לחץ כאן לבחירה...")
        login_pin = st.text_input("קוד אישי", type="password")
        if st.form_submit_button("כניסה"):
            if login_name:
                u_match = users_df[users_df["name"] == login_name]
                if not u_match.empty and str(login_pin).strip() == u_match.iloc[0]["pin"]:
                    st.session_state.user = u_match.iloc[0].to_dict()
                    st.session_state.logout_in_progress = False
                    cookie_manager.set("soda_user_name", login_name, expires_at=datetime.now().replace(year=datetime.now().year + 1))
                    st.cache_data.clear()
                    st.rerun()
                else: st.error("קוד שגוי.")
            else: st.warning("בחר שם מהרשימה.")

else:
    user = st.session_state.user
    is_admin = user.get('role') == 'admin'
    tabs = st.tabs(["👤 החשבון שלי", "🛠️ ניהול"]) if is_admin else [st.container()]

    with tabs[0]:
        st.header(f"שלום, {user['name']}")
        
        # חישוב חוב
        u_t = trans_df[trans_df["name"] == user["name"]] if not trans_df.empty else pd.DataFrame()
        p_sum = u_t[u_t["type"] == "purchase"]["amount"].sum()
        pay_sum = u_t[(u_t["type"] == "payment") & (u_t["status"] == "completed")]["amount"].sum()
        adj_sum = u_t[u_t["type"] == "adjustment"]["amount"].sum()
        pend_sum = u_t[(u_t["type"] == "payment") & (u_t["status"] == "pending")]["amount"].sum()
        
        balance = p_sum + adj_sum - pay_sum
        
        c1, c2, c3 = st.columns(3)
        c1.metric("חוב נוכחי", f"₪{balance:.2f}")
        c2.metric("מחיר בקבוק", f"₪{bottle_price}")
        if pend_sum > 0: c3.warning(f"באישור: ₪{pend_sum}")

        st.divider()

        # קנייה מרובה
        with st.expander("🥤 לקחתי בקבוק סודה", expanded=True):
            col_q1, col_q2 = st.columns([1, 2])
            qty = col_q1.number_input("כמות", min_value=1, value=1, step=1)
            if col_q2.button(f"אשר קנייה (₪{qty*bottle_price:.2f})", type="primary"):
                new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": user["name"], "type": "purchase", "amount": qty*bottle_price, "status": "completed", "notes": ""}])
                if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()
        
        # הפקדה
        with st.expander("💳 טעינת כסף (הפקדה)"):
            with st.form("pay_f", clear_on_submit=True):
                p_amt = st.number_input("סכום (₪)", min_value=1.0, value=20.0, step=1.0)
                if st.form_submit_button("שלח בקשת טעינה"):
                    new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": user["name"], "type": "payment", "amount": p_amt, "status": "pending", "notes": ""}])
                    if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()

        st.subheader("היסטוריה אישית")
        if not u_t.empty: st.dataframe(u_t.sort_values("timestamp", ascending=False), use_container_width=True)
        
        if st.button("🚪 התנתק"):
            cookie_manager.delete("soda_user_name")
            st.session_state.logout_in_progress = True
            if "user" in st.session_state: del st.session_state.user
            st.cache_data.clear()
            st.rerun()

    if is_admin:
        with tabs[1]:
            st.header("ניהול מנהל")
            
            # 1. אישור הפקדות
            st.subheader("💳 הפקדות לאישור")
            p_df = trans_df[trans_df["status"] == "pending"] if "status" in trans_df.columns else pd.DataFrame()
            if not p_df.empty:
                for idx, row in p_df.iterrows():
                    ca, cb = st.columns([3, 1])
                    ca.write(f"**{row['name']}**: ₪{row['amount']}")
                    if cb.button("אשר", key=f"ap_{idx}"):
                        trans_df.at[idx, "status"] = "completed"
                        if safe_update("Transactions", trans_df): st.rerun()
            else: st.write("אין הפקדות ממתינות.")

            # 2. עדכון חוב ידני
            with st.expander("💸 עדכון חוב ידני (פיצוי/תיקון)"):
                with st.form("adj_f"):
                    t_user = st.selectbox("בחר משתמש", users_df["name"].tolist())
                    t_amt = st.number_input("סכום לשינוי (חיובי מוסיף חוב, שלילי מוריד חוב)", value=0.0)
                    t_note = st.text_input("סיבה")
                    if st.form_submit_button("בצע עדכון"):
                        if t_amt != 0:
                            new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": t_user, "type": "adjustment", "amount": t_amt, "status": "completed", "notes": t_note}])
                            if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()

            st.divider()

            # 3. מלאי ומחיר
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("מלאי")
                stock = inv_df['quantity'].sum() - len(trans_df[trans_df['type'] == 'purchase']) if not inv_df.empty else 0
                st.metric("במקרר", int(stock))
                with st.form("inv_f"):
                    qc = st.number_input("שינוי מלאי (+/-)", value=0)
                    if st.form_submit_button("עדכן מלאי"):
                        new_i = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "quantity": qc}])
                        if safe_update("Inventory", pd.concat([inv_df, new_i], ignore_index=True)): st.rerun()
            
            with col_b:
                st.subheader("מחיר")
                with st.form("pr_f"):
                    np = st.number_input("מחיר חדש", value=bottle_price)
                    if st.form_submit_button("שמור מחיר"):
                        s_new = conn.read(worksheet="Settings", ttl=0)
                        s_new.loc[s_new['key'] == 'bottle_price', 'value'] = np
                        if safe_update("Settings", s_new): st.rerun()

            st.divider()

            # 4. הוספת משתמש
            with st.expander("👤 הוספת משתמש"):
                with st.form("add_u"):
                    nn = st.text_input("שם מלא")
                    np = st.text_input("קוד (4 ספרות)")
                    nr = st.selectbox("תפקיד", ["user", "admin"])
                    if st.form_submit_button("הוסף"):
                        if nn and len(np) == 4:
                            new_u = pd.DataFrame([{"name": nn, "pin": np, "role": nr}])
                            if safe_update("Users", pd.concat([users_df, new_u], ignore_index=True)): st.rerun()

            st.subheader("טבלת חובות")
            if not users_df.empty:
                sums = []
                for _, u in users_df.iterrows():
                    u_t_all = trans_df[trans_df["name"] == u["name"]]
                    d = u_t_all[u_t_all["type"] == "purchase"]["amount"].sum() + u_t_all[u_t_all["type"] == "adjustment"]["amount"].sum() - u_t_all[(u_t_all["type"] == "payment") & (u_t_all["status"] == "completed")]["amount"].sum()
                    sums.append({"שם": u["name"], "חוב": f"₪{d:.2f}"})
                st.table(pd.DataFrame(sums).sort_values("חוב", ascending=False))
