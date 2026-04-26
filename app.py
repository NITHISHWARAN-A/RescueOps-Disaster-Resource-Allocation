import os
import re
import sqlite3
import json
import smtplib


try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import timedelta
from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, session, g)
from werkzeug.security import generate_password_hash, check_password_hash
import pulp

app = Flask(__name__)
app.secret_key = os.environ.get('APP_SECRET', 'rescueops_secret_key_2026_v5')

# FIX 8: 1-hour session — survives page refresh without logout
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)
app.config['SESSION_COOKIE_HTTPONLY']    = True
app.config['SESSION_COOKIE_SAMESITE']   = 'Lax'

@app.before_request
def keep_session_alive():
    session.permanent = True

DATABASE      = 'rescueops.db'
EMAIL_SENDER  = 'rescueops.support@gmail.com'
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')
SMTP_SERVER   = 'smtp.gmail.com'
SMTP_PORT     = 587

INDIA_LOCATIONS = {
    "Andhra Pradesh":  ["Visakhapatnam","Vijayawada","Guntur","Nellore","Kurnool","Tirupati","Kadapa","Anantapur","Eluru","Rajahmundry"],
    "Assam":           ["Guwahati","Silchar","Dibrugarh","Jorhat","Nagaon","Tinsukia","Tezpur","Bongaigaon","Dhubri","Karimganj"],
    "Bihar":           ["Patna","Gaya","Bhagalpur","Muzaffarpur","Darbhanga","Purnia","Begusarai","Katihar","Arrah","Samastipur"],
    "Gujarat":         ["Ahmedabad","Surat","Vadodara","Rajkot","Bhavnagar","Jamnagar","Gandhinagar","Anand","Morbi","Bharuch"],
    "Karnataka":       ["Bengaluru","Mysuru","Hubballi","Mangaluru","Belagavi","Kalaburagi","Ballari","Vijayapura","Shivamogga","Tumakuru"],
    "Kerala":          ["Thiruvananthapuram","Kochi","Kozhikode","Thrissur","Kollam","Palakkad","Alappuzha","Kannur","Malappuram","Kottayam"],
    "Madhya Pradesh":  ["Bhopal","Indore","Gwalior","Jabalpur","Ujjain","Sagar","Ratlam","Rewa","Satna","Dewas"],
    "Maharashtra":     ["Mumbai","Pune","Nagpur","Nashik","Aurangabad","Solapur","Kolhapur","Amravati","Nanded","Jalgaon"],
    "Odisha":          ["Bhubaneswar","Cuttack","Rourkela","Berhampur","Sambalpur","Puri","Balasore","Bhadrak","Baripada","Jharsuguda"],
    "Rajasthan":       ["Jaipur","Jodhpur","Udaipur","Kota","Bikaner","Ajmer","Alwar","Bharatpur","Sikar","Sri Ganganagar"],
    "Tamil Nadu":      ["Chennai","Coimbatore","Madurai","Tiruchirappalli","Salem","Tirunelveli","Vellore","Erode","Thoothukudi","Dindigul","Thanjavur","Tirupur","Kancheepuram","Cuddalore","Krishnagiri","Namakkal","Nagapattinam","Ramanathapuram","Villupuram","Sivaganga"],
    "Telangana":       ["Hyderabad","Warangal","Nizamabad","Karimnagar","Khammam","Ramagundam","Mahabubnagar","Nalgonda","Adilabad","Suryapet"],
    "Uttar Pradesh":   ["Lucknow","Kanpur","Agra","Varanasi","Prayagraj","Meerut","Noida","Ghaziabad","Bareilly","Aligarh"],
    "West Bengal":     ["Kolkata","Howrah","Durgapur","Asansol","Siliguri","Bardhaman","Malda","Barasat","Kharagpur","Haldia"],
    "Jammu & Kashmir": ["Srinagar","Jammu","Anantnag","Baramulla","Sopore","Kathua","Udhampur","Rajouri","Poonch","Kargil"],
    "Himachal Pradesh":["Shimla","Manali","Dharamsala","Kullu","Mandi","Solan","Kangra","Una","Hamirpur","Chamba"],
    "Uttarakhand":     ["Dehradun","Haridwar","Rishikesh","Roorkee","Haldwani","Kashipur","Rudrapur","Nainital","Almora","Pithoragarh"],
    "Goa":             ["Panaji","Margao","Vasco da Gama","Mapusa","Ponda","Bicholim","Canacona","Quepem","Sanquelim","Valpoi"],
    "Manipur":         ["Imphal","Thoubal","Churachandpur","Bishnupur","Senapati","Ukhrul","Tamenglong","Jiribam","Chandel","Kangpokpi"],
    "Meghalaya":       ["Shillong","Tura","Jowai","Baghmara","Nongstoin","Williamnagar","Resubelpara","Ampati","Mairang","Mawkyrwat"],
    "Mizoram":         ["Aizawl","Lunglei","Champhai","Serchhip","Kolasib","Lawngtlai","Mamit","Saitual","Siaha","Khawzawl"],
    "Nagaland":        ["Kohima","Dimapur","Mokokchung","Wokha","Zunheboto","Tuensang","Mon","Phek","Longleng","Kiphire"],
    "Sikkim":          ["Gangtok","Namchi","Gyalshing","Mangan","Rangpo","Jorethang","Nayabazar","Ravangla","Yuksom","Chungthang"],
    "Tripura":         ["Agartala","Dharmanagar","Udaipur","Kailashahar","Belonia","Khowai","Ambassa","Sabroom","Sonamura","Bishalgarh"],
}

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def r2d(row):  return dict(row) if row else None
def r2l(rows): return [dict(r) for r in rows]

def init_db():
    with app.app_context():
        db = get_db(); c = db.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, full_name TEXT DEFAULT 'Admin', email TEXT DEFAULT '',
            security_question TEXT DEFAULT 'What is the system name?',
            security_answer TEXT DEFAULT '')''')
        c.execute('''CREATE TABLE IF NOT EXISTS shelters (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL,
            email TEXT DEFAULT '', phone TEXT DEFAULT '', location TEXT DEFAULT '',
            state TEXT DEFAULT '', district TEXT DEFAULT '', village TEXT DEFAULT '',
            capacity INTEGER DEFAULT 0, current_occupants INTEGER DEFAULT 0,
            security_question TEXT DEFAULT '', security_answer TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT UNIQUE NOT NULL,
            item_name TEXT NOT NULL, category TEXT NOT NULL, unit TEXT NOT NULL,
            total_stock INTEGER DEFAULT 0, allocated INTEGER DEFAULT 0,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shelter_id INTEGER NOT NULL,
            username TEXT NOT NULL, disaster_type TEXT DEFAULT 'General',
            priority TEXT DEFAULT 'Normal', transport_mode TEXT DEFAULT 'Lorry',
            transport_detail TEXT DEFAULT '', adults_male INTEGER DEFAULT 0,
            adults_female INTEGER DEFAULT 0, children_boys INTEGER DEFAULT 0,
            children_girls INTEGER DEFAULT 0, elderly_male INTEGER DEFAULT 0,
            elderly_female INTEGER DEFAULT 0, pregnant_women INTEGER DEFAULT 0,
            special_needs INTEGER DEFAULT 0, breakfast_packs INTEGER DEFAULT 0,
            lunch_packs INTEGER DEFAULT 0, dinner_packs INTEGER DEFAULT 0,
            snack_packs INTEGER DEFAULT 0, baby_food_kg INTEGER DEFAULT 0,
            rice_kg INTEGER DEFAULT 0, dal_kg INTEGER DEFAULT 0,
            cooking_oil_L INTEGER DEFAULT 0, water_bottles_500ml INTEGER DEFAULT 0,
            water_cans_20L INTEGER DEFAULT 0, water_purify_tabs INTEGER DEFAULT 0,
            first_aid_kits INTEGER DEFAULT 0, antibiotics_strip INTEGER DEFAULT 0,
            paracetamol_strip INTEGER DEFAULT 0, ors_packets INTEGER DEFAULT 0,
            iv_fluid_bottles INTEGER DEFAULT 0, bandage_rolls INTEGER DEFAULT 0,
            mens_shirts INTEGER DEFAULT 0, mens_pants INTEGER DEFAULT 0,
            womens_saree INTEGER DEFAULT 0, womens_churidar INTEGER DEFAULT 0,
            boys_set INTEGER DEFAULT 0, girls_set INTEGER DEFAULT 0,
            infant_set INTEGER DEFAULT 0, family_tents INTEGER DEFAULT 0,
            tarpaulin_sheets INTEGER DEFAULT 0, sleeping_mats INTEGER DEFAULT 0,
            blankets INTEGER DEFAULT 0, petrol_L INTEGER DEFAULT 0,
            diesel_L INTEGER DEFAULT 0, lpg_cylinders INTEGER DEFAULT 0,
            generators INTEGER DEFAULT 0, batteries_set INTEGER DEFAULT 0,
            solar_lanterns INTEGER DEFAULT 0, sanitation_kits INTEGER DEFAULT 0,
            toiletries_kit INTEGER DEFAULT 0, rescue_ropes INTEGER DEFAULT 0,
            shovels INTEGER DEFAULT 0, notes TEXT DEFAULT '', status TEXT DEFAULT 'Pending',
            admin_notes TEXT DEFAULT '', created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME)''')
        c.execute('''CREATE TABLE IF NOT EXISTS dispatch_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER NOT NULL,
            shelter_id INTEGER NOT NULL, username TEXT NOT NULL,
            urgency_score REAL DEFAULT 0, urgency_pct REAL DEFAULT 0,
            capacity_used REAL DEFAULT 0, utilization_pct REAL DEFAULT 0,
            transport_mode TEXT DEFAULT 'Lorry', dispatch_detail TEXT DEFAULT '',
            unmet_detail TEXT DEFAULT '', timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS tracking_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER NOT NULL,
            shelter_id INTEGER NOT NULL, update_type TEXT NOT NULL,
            message TEXT NOT NULL, location_tag TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        c.execute("SELECT id FROM admins WHERE username='admin'")
        if not c.fetchone():
            c.execute('''INSERT INTO admins (username,password,full_name,email,security_question,security_answer)
                         VALUES (?,?,?,?,?,?)''',
                      ('admin', generate_password_hash('admin123'), 'System Administrator',
                       'admin@rescueops.in', 'What is the system name?',
                       generate_password_hash('rescueops')))
        items = [
            ('breakfast_packs','Breakfast Packs (Idli/Dosa/Upma)','Food','Packs'),
            ('lunch_packs','Lunch Packs (Rice + Curry)','Food','Packs'),
            ('dinner_packs','Dinner Packs (Chapati/Rice)','Food','Packs'),
            ('snack_packs','Snack Packs (Biscuits/Fruits)','Food','Packs'),
            ('baby_food_kg','Baby Food / Cereal','Food','Kg'),
            ('rice_kg','Raw Rice','Food','Kg'),('dal_kg','Dal / Lentils','Food','Kg'),
            ('cooking_oil_L','Cooking Oil','Food','Litres'),
            ('water_bottles_500ml','Water Bottles 500ml','Water','Bottles'),
            ('water_cans_20L','Water Cans 20L','Water','Cans'),
            ('water_purify_tabs','Water Purification Tablets','Water','Strips'),
            ('first_aid_kits','First Aid Kits','Medicine','Kits'),
            ('antibiotics_strip','Antibiotics (Strip)','Medicine','Strips'),
            ('paracetamol_strip','Paracetamol 500mg (Strip)','Medicine','Strips'),
            ('ors_packets','ORS Packets','Medicine','Packets'),
            ('iv_fluid_bottles','IV Fluid Bottles (500ml)','Medicine','Bottles'),
            ('bandage_rolls','Bandage Rolls','Medicine','Rolls'),
            ("mens_shirts","Men's Shirts",'Clothing','Pieces'),
            ("mens_pants","Men's Pants / Lungi",'Clothing','Pieces'),
            ("womens_saree","Women's Sarees",'Clothing','Pieces'),
            ("womens_churidar","Women's Churidar Sets",'Clothing','Sets'),
            ("boys_set","Boys' Clothing Set (6-14 yrs)",'Clothing','Sets'),
            ("girls_set","Girls' Clothing Set (6-14 yrs)",'Clothing','Sets'),
            ("infant_set","Infant Clothing Set (0-5 yrs)",'Clothing','Sets'),
            ('family_tents','Family Tents (4-6 person)','Shelter','Tents'),
            ('tarpaulin_sheets','Tarpaulin Sheets','Shelter','Sheets'),
            ('sleeping_mats','Sleeping Mats','Shelter','Mats'),
            ('blankets','Blankets / Quilts','Shelter','Pieces'),
            ('petrol_L','Petrol','Fuel','Litres'),('diesel_L','Diesel','Fuel','Litres'),
            ('lpg_cylinders','LPG Cylinders (14.2kg)','Fuel','Cylinders'),
            ('generators','Portable Generators','Equipment','Units'),
            ('batteries_set','Battery / Power Bank Sets','Equipment','Sets'),
            ('solar_lanterns','Solar Lanterns','Equipment','Units'),
            ('sanitation_kits','Sanitation Kits','Sanitation','Kits'),
            ('toiletries_kit','Toiletries Kit','Sanitation','Kits'),
            ('rescue_ropes','Rescue Ropes (20m rolls)','Tools','Rolls'),
            ('shovels','Shovels / Spades','Tools','Units'),
        ]
        for code, name, cat, unit in items:
            c.execute('INSERT OR IGNORE INTO inventory (item_code,item_name,category,unit) VALUES (?,?,?,?)',
                      (code, name, cat, unit))
        db.commit()

init_db()

ITEM_CONFIG = {
    'breakfast_packs':{'weight_kg':0.8,'priority':9},'lunch_packs':{'weight_kg':1.2,'priority':9},
    'dinner_packs':{'weight_kg':1.2,'priority':9},'snack_packs':{'weight_kg':0.5,'priority':6},
    'baby_food_kg':{'weight_kg':1.0,'priority':10},'rice_kg':{'weight_kg':1.0,'priority':7},
    'dal_kg':{'weight_kg':1.0,'priority':7},'cooking_oil_L':{'weight_kg':0.9,'priority':5},
    'water_bottles_500ml':{'weight_kg':0.5,'priority':10},'water_cans_20L':{'weight_kg':20.0,'priority':9},
    'water_purify_tabs':{'weight_kg':0.05,'priority':8},'first_aid_kits':{'weight_kg':2.0,'priority':10},
    'antibiotics_strip':{'weight_kg':0.05,'priority':9},'paracetamol_strip':{'weight_kg':0.05,'priority':8},
    'ors_packets':{'weight_kg':0.05,'priority':9},'iv_fluid_bottles':{'weight_kg':0.6,'priority':10},
    'bandage_rolls':{'weight_kg':0.15,'priority':8},'mens_shirts':{'weight_kg':0.3,'priority':4},
    'mens_pants':{'weight_kg':0.5,'priority':4},'womens_saree':{'weight_kg':0.6,'priority':4},
    'womens_churidar':{'weight_kg':0.5,'priority':4},'boys_set':{'weight_kg':0.4,'priority':5},
    'girls_set':{'weight_kg':0.4,'priority':5},'infant_set':{'weight_kg':0.25,'priority':6},
    'family_tents':{'weight_kg':15.0,'priority':7},'tarpaulin_sheets':{'weight_kg':2.5,'priority':6},
    'sleeping_mats':{'weight_kg':1.2,'priority':5},'blankets':{'weight_kg':0.8,'priority':6},
    'petrol_L':{'weight_kg':0.75,'priority':7},'diesel_L':{'weight_kg':0.85,'priority':7},
    'lpg_cylinders':{'weight_kg':15.0,'priority':6},'generators':{'weight_kg':50.0,'priority':5},
    'batteries_set':{'weight_kg':1.5,'priority':4},'solar_lanterns':{'weight_kg':0.4,'priority':5},
    'sanitation_kits':{'weight_kg':0.8,'priority':7},'toiletries_kit':{'weight_kg':0.6,'priority':5},
    'rescue_ropes':{'weight_kg':1.8,'priority':6},'shovels':{'weight_kg':2.0,'priority':5},
}
TRANSPORT_CONFIG = {
    'Lorry':{'max_kg':5000,'emoji':'🚛','type':'Land'},'Mini_Van':{'max_kg':1500,'emoji':'🚐','type':'Land'},
    'Tractor':{'max_kg':2000,'emoji':'🚜','type':'Land'},'Ambulance':{'max_kg':300,'emoji':'🚑','type':'Land'},
    'Bullock_Cart':{'max_kg':400,'emoji':'🐂','type':'Land'},'Manual':{'max_kg':150,'emoji':'🧑','type':'Land'},
    'Boat':{'max_kg':800,'emoji':'⛵','type':'Water'},'Motorboat':{'max_kg':300,'emoji':'🚤','type':'Water'},
    'Helicopter':{'max_kg':900,'emoji':'🚁','type':'Air'},'Fixed_Wing':{'max_kg':3000,'emoji':'✈️','type':'Air'},
    'Drone':{'max_kg':10,'emoji':'🛸','type':'Air'},
}
CATEGORY_MULTIPLIERS = {
    'Hospital':2.5,'Field Clinic':2.3,'Maternity Center':2.2,'Rescue Team':2.0,
    'NDRF Camp':1.9,'Old Age Home':1.9,'Disability Center':1.9,'Police Camp':1.8,
    'Army Camp':1.8,'Orphanage':1.8,'School Shelter':1.7,'Community Hall':1.5,
    'Shelter Camp':1.5,'Distribution Center':1.3,'General':1.0
}
MAX_URGENCY = 1000.0

def calculate_urgency(row):
    s  = int(row.get('adults_male',0) or 0)*1.0 + int(row.get('adults_female',0) or 0)*1.2
    s += int(row.get('children_boys',0) or 0)*2.5 + int(row.get('children_girls',0) or 0)*2.5
    s += int(row.get('elderly_male',0) or 0)*2.0 + int(row.get('elderly_female',0) or 0)*2.0
    s += int(row.get('pregnant_women',0) or 0)*3.5 + int(row.get('special_needs',0) or 0)*3.0
    s += {'Flood':30,'Earthquake':40,'Cyclone':35,'Tsunami':45,'Landslide':30,'Fire':25,'Pandemic':20,'Drought':15,'General':0}.get(row.get('disaster_type','General'),0)
    s += {'Critical':50,'High':30,'Normal':0,'Low':-10}.get(row.get('priority','Normal'),0)
    return round(s, 2)

def run_lp_knapsack(request_row, inv_snap, capacity_kg, category):
    multiplier = CATEGORY_MULTIPLIERS.get(category, 1.0)
    items, no_stock = [], []
    for code, cfg in ITEM_CONFIG.items():
        req_qty = int(request_row.get(code, 0) or 0)
        if req_qty <= 0: continue
        avail = int(inv_snap.get(code, 0))
        if avail <= 0: no_stock.append({'code':code,'requested':req_qty}); continue
        feasible = min(req_qty, avail)
        items.append({'code':code,'requested':req_qty,'available':avail,'feasible':feasible,
                      'weight_kg':cfg['weight_kg'],'priority':cfg['priority']})
    unmet = {i['code']:i['requested'] for i in no_stock}
    if not items: return {}, unmet, []
    prob  = pulp.LpProblem("RescueOps_LP_Knapsack", pulp.LpMaximize)
    vars_ = {i['code']: pulp.LpVariable(f"x_{i['code']}",lowBound=0,upBound=i['feasible'],cat='Integer') for i in items}
    prob += pulp.lpSum(vars_[i['code']]*i['priority']*multiplier for i in items)
    prob += pulp.lpSum(vars_[i['code']]*i['weight_kg'] for i in items) <= capacity_kg
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    allocated = {}
    if pulp.LpStatus[prob.status] == 'Optimal':
        for item in items:
            raw  = vars_[item['code']].varValue
            sent = int(round(raw)) if raw is not None else 0
            sent = max(0, min(sent, item['feasible']))
            allocated[item['code']] = sent
            short = item['requested'] - sent
            if short > 0: unmet[item['code']] = short
    else:
        for item in items: allocated[item['code']] = 0; unmet[item['code']] = item['requested']
    return allocated, unmet, items

# ── ROUTES ──
@app.route('/')
def index(): return render_template('index.html')

@app.route('/admin/login')
def admin_login(): return render_template('admin_login.html')

@app.route('/shelter/login')
def shelter_login(): return render_template('shelter_login.html')

@app.route('/shelter/register')
def shelter_register():
    return render_template('shelter_register.html', states=sorted(INDIA_LOCATIONS.keys()),
                           locations_json=json.dumps(INDIA_LOCATIONS))

@app.route('/forgot_password')
def forgot_password(): return render_template('forgot_password.html')

@app.route('/shelter/profile')
def shelter_profile():
    if session.get('role') != 'shelter': return redirect(url_for('shelter_login'))
    db = get_db()
    shelter = r2d(db.execute("SELECT * FROM shelters WHERE username=?", (session['user'],)).fetchone())
    return render_template('shelter_profile.html', shelter=shelter,
                           states=sorted(INDIA_LOCATIONS.keys()),
                           locations_json=json.dumps(INDIA_LOCATIONS))

@app.route('/admin/view_database')
def view_database():
    if session.get('role') != 'admin': return redirect(url_for('admin_login'))
    db = get_db()
    return render_template('view_database.html',
        shelters  = r2l(db.execute("SELECT id,username,name,category,state,district,email,phone,capacity,created_at FROM shelters ORDER BY id DESC").fetchall()),
        requests  = r2l(db.execute("SELECT id,username,disaster_type,priority,transport_mode,status,created_at,resolved_at FROM requests ORDER BY id DESC LIMIT 200").fetchall()),
        inventory = r2l(db.execute("SELECT item_code,item_name,category,unit,total_stock,allocated FROM inventory ORDER BY category,item_name").fetchall()),
        logs      = r2l(db.execute("SELECT id,request_id,username,urgency_score,urgency_pct,capacity_used,utilization_pct,transport_mode,timestamp FROM dispatch_logs ORDER BY id DESC LIMIT 100").fetchall()))

# Auth APIs
@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    d = request.json or {}
    db = get_db()
    admin = db.execute("SELECT * FROM admins WHERE username=?", (d.get('username'),)).fetchone()
    if admin and check_password_hash(admin['password'], d.get('password','')):
        session.update({'user':admin['username'],'role':'admin','full_name':admin['full_name']})
        return jsonify({'status':'success','redirect':url_for('admin_dashboard')})
    return jsonify({'status':'error','message':'Invalid admin credentials'}), 401

@app.route('/api/shelter/login', methods=['POST'])
def api_shelter_login():
    d = request.json or {}
    db = get_db()
    shelter = db.execute("SELECT * FROM shelters WHERE username=?", (d.get('username'),)).fetchone()
    if shelter and check_password_hash(shelter['password'], d.get('password','')):
        session.update({'user':shelter['username'],'role':'shelter',
                        'shelter_id':shelter['id'],'category':shelter['category'],'shelter_name':shelter['name']})
        return jsonify({'status':'success','redirect':url_for('shelter_dashboard')})
    return jsonify({'status':'error','message':'Invalid shelter credentials'}), 401

@app.route('/api/shelter/register', methods=['POST'])
def api_shelter_register():
    d = request.json or {}
    if len(d.get('password','')) < 6:
        return jsonify({'status':'error','message':'Password must be at least 6 characters'}), 400
    db = get_db()
    try:
        db.execute('''INSERT INTO shelters (username,password,name,category,email,phone,location,
                       state,district,village,capacity,security_question,security_answer)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (d['username'],generate_password_hash(d['password']),d['name'],d['category'],
             d.get('email',''),d.get('phone',''),d.get('location',''),d.get('state',''),
             d.get('district',''),d.get('village',''),int(d.get('capacity',0)),
             d.get('security_question',''),generate_password_hash(d.get('security_answer','na').lower())))
        db.commit()
        return jsonify({'status':'success'})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)}), 400

@app.route('/api/get_security_question', methods=['POST'])
def api_get_security_question():
    d = request.json or {}
    db = get_db()
    tbl = 'admins' if d.get('role')=='admin' else 'shelters'
    row = db.execute(f"SELECT security_question FROM {tbl} WHERE username=?", (d.get('username'),)).fetchone()
    if not row: return jsonify({'status':'error','message':'Username not found'}), 404
    return jsonify({'status':'success','question':row['security_question']})

@app.route('/api/forgot_password', methods=['POST'])
def api_forgot_password():
    d = request.json or {}
    role, username = d.get('role','shelter'), d.get('username','').strip()
    answer, new_pw = d.get('answer','').strip().lower(), d.get('new_password','').strip()
    if len(new_pw) < 6: return jsonify({'status':'error','message':'Password must be at least 6 characters'}), 400
    db  = get_db()
    tbl = 'admins' if role=='admin' else 'shelters'
    row = db.execute(f"SELECT * FROM {tbl} WHERE username=?", (username,)).fetchone()
    if not row: return jsonify({'status':'error','message':'Username not found'}), 404
    if not check_password_hash(row['security_answer'], answer):
        return jsonify({'status':'error','message':'Incorrect security answer'}), 401
    db.execute(f"UPDATE {tbl} SET password=? WHERE username=?", (generate_password_hash(new_pw), username))
    db.commit()
    return jsonify({'status':'success','message':'Password reset successful'})

# Shelter APIs
@app.route('/shelter/dashboard')
def shelter_dashboard():
    if session.get('role') != 'shelter': return redirect(url_for('shelter_login'))
    db = get_db()
    shelter   = r2d(db.execute("SELECT * FROM shelters WHERE username=?", (session['user'],)).fetchone())
    my_reqs   = r2l(db.execute("SELECT * FROM requests WHERE username=? ORDER BY id DESC", (session['user'],)).fetchall())
    inventory = r2l(db.execute("SELECT * FROM inventory ORDER BY category, item_name").fetchall())
    tracking  = r2l(db.execute("SELECT * FROM tracking_updates WHERE shelter_id=? ORDER BY created_at DESC LIMIT 30", (session['shelter_id'],)).fetchall())
    return render_template('shelter_dashboard.html', shelter=shelter, my_requests=my_reqs, inventory=inventory, tracking=tracking)

@app.route('/api/submit_request', methods=['POST'])
def submit_request():
    if session.get('role') != 'shelter': return jsonify({'error':'Unauthorized'}), 401
    d = request.json or {}
    db = get_db()
    fields = list(ITEM_CONFIG.keys())
    cols = ','.join(['shelter_id','username','disaster_type','priority','transport_mode','transport_detail',
                     'adults_male','adults_female','children_boys','children_girls','elderly_male',
                     'elderly_female','pregnant_women','special_needs','notes'] + fields)
    ph   = ','.join(['?']*(15+len(fields)))
    vals = [session['shelter_id'],session['user'],d.get('disaster_type','General'),d.get('priority','Normal'),
            d.get('transport_mode','Lorry'),d.get('transport_detail',''),
            int(d.get('adults_male',0)),int(d.get('adults_female',0)),int(d.get('children_boys',0)),
            int(d.get('children_girls',0)),int(d.get('elderly_male',0)),int(d.get('elderly_female',0)),
            int(d.get('pregnant_women',0)),int(d.get('special_needs',0)),d.get('notes','')
           ] + [int(d.get(f,0)) for f in fields]
    cursor = db.execute(f'INSERT INTO requests ({cols}) VALUES ({ph})', vals)
    db.commit()
    return jsonify({'status':'success','request_id':cursor.lastrowid})

@app.route('/api/shelter/update_profile', methods=['POST'])
def update_shelter_profile():
    if session.get('role') != 'shelter': return jsonify({'error':'Unauthorized'}), 401
    d = request.json or {}
    db = get_db()
    db.execute('''UPDATE shelters SET name=?,category=?,email=?,phone=?,state=?,district=?,village=?,capacity=?,location=? WHERE username=?''',
               (d['name'],d['category'],d.get('email',''),d.get('phone',''),d.get('state',''),
                d.get('district',''),d.get('village',''),int(d.get('capacity',0)),d.get('location',''),session['user']))
    db.commit()
    return jsonify({'status':'success'})

@app.route('/api/shelter/latest_status')
def shelter_latest_status():
    if session.get('role') != 'shelter': return jsonify({'status':'logged_out'}), 401
    db = get_db()
    reqs = r2l(db.execute("SELECT id,status,admin_notes,disaster_type,priority,transport_mode,created_at FROM requests WHERE username=? ORDER BY id DESC", (session['user'],)).fetchall())
    tracking = r2l(db.execute("SELECT * FROM tracking_updates WHERE shelter_id=? ORDER BY created_at DESC LIMIT 30", (session['shelter_id'],)).fetchall())
    return jsonify({'requests':reqs,'tracking':tracking})

# Admin APIs
@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin': return redirect(url_for('admin_login'))
    db = get_db()
    all_requests  = r2l(db.execute('''SELECT r.*, s.name AS shelter_name, s.category, s.location, s.state, s.district, s.village, s.phone AS shelter_phone, s.email AS shelter_email FROM requests r JOIN shelters s ON r.shelter_id=s.id ORDER BY CASE r.priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Normal' THEN 3 ELSE 4 END, r.created_at DESC''').fetchall())
    inventory     = r2l(db.execute("SELECT * FROM inventory ORDER BY category, item_name").fetchall())
    dispatch_logs = r2l(db.execute('''SELECT d.*, s.name AS shelter_name, r.disaster_type, r.priority FROM dispatch_logs d JOIN shelters s ON d.shelter_id=s.id JOIN requests r ON d.request_id=r.id ORDER BY d.timestamp DESC LIMIT 100''').fetchall())
    shelters_list = r2l(db.execute("SELECT * FROM shelters ORDER BY name").fetchall())
    stats = {'total':len(all_requests),'pending':sum(1 for r in all_requests if r['status']=='Pending'),
             'dispatched':sum(1 for r in all_requests if r['status']=='Dispatched'),
             'critical':sum(1 for r in all_requests if r['priority']=='Critical'),
             'by_category':{},'by_disaster':{},'utilization_trend':[]}
    for r in all_requests:
        stats['by_category'][r['category']] = stats['by_category'].get(r['category'],0)+1
        stats['by_disaster'][r['disaster_type']] = stats['by_disaster'].get(r['disaster_type'],0)+1
    for log in dispatch_logs[-10:]:
        stats['utilization_trend'].append(log['utilization_pct'])
    return render_template('admin_dashboard.html', requests=all_requests, inventory=inventory,
                           dispatch_logs=dispatch_logs, shelters=shelters_list,
                           stats=stats, transport_config=TRANSPORT_CONFIG)

@app.route('/api/admin/update_inventory', methods=['POST'])
def update_inventory():
    if session.get('role') != 'admin': return jsonify({'error':'Unauthorized'}), 401
    d = request.json or {}
    db = get_db()
    db.execute("UPDATE inventory SET total_stock=?,last_updated=CURRENT_TIMESTAMP WHERE item_code=?", (int(d['stock']),d['item_code']))
    db.commit()
    item = r2d(db.execute("SELECT * FROM inventory WHERE item_code=?", (d['item_code'],)).fetchone())
    return jsonify({'status':'success','available':item['total_stock']-item['allocated']})

@app.route('/api/admin/bulk_save_stock', methods=['POST'])
def bulk_save_stock():
    if session.get('role') != 'admin': return jsonify({'error':'Unauthorized'}), 401
    d = request.json or {}
    db = get_db(); updated = 0
    for item in d.get('items',[]):
        try:
            db.execute("UPDATE inventory SET total_stock=?,last_updated=CURRENT_TIMESTAMP WHERE item_code=?", (int(item['stock']),item['item_code']))
            updated += 1
        except Exception: continue
    db.commit()
    return jsonify({'status':'success','updated':updated})

@app.route('/api/admin/delete_inventory_item', methods=['POST'])
def delete_inventory_item():
    if session.get('role') != 'admin': return jsonify({'error':'Unauthorized'}), 401
    d = request.json or {}
    db = get_db()
    db.execute("DELETE FROM inventory WHERE item_code=?", (d['item_code'],))
    db.commit()
    return jsonify({'status':'success'})

@app.route('/api/admin/add_inventory_item', methods=['POST'])
def add_inventory_item():
    if session.get('role') != 'admin': return jsonify({'error':'Unauthorized'}), 401
    d = request.json or {}
    name = (d.get('item_name') or '').strip()
    if not name: return jsonify({'status':'error','message':'Item name is required'}), 400
    code = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')[:40]
    db = get_db()
    try:
        db.execute("INSERT INTO inventory (item_code,item_name,category,unit,total_stock) VALUES (?,?,?,?,?)",
                   (code, name, d.get('category','General'), d.get('unit','Units'), int(d.get('total_stock',0))))
        db.commit()
        return jsonify({'status':'success','item_code':code})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)}), 400

@app.route('/api/admin/optimize', methods=['POST'])
def optimize():
    if session.get('role') != 'admin': return jsonify({'error':'Unauthorized'}), 401
    d = request.json or {}
    req_id = int(d['request_id']); capacity = float(d['capacity_kg'])
    db  = get_db()
    row = r2d(db.execute('''SELECT r.*, s.category, s.email AS shelter_email FROM requests r JOIN shelters s ON r.shelter_id=s.id WHERE r.id=?''', (req_id,)).fetchone())
    if not row: return jsonify({'status':'error','message':'Request not found'}), 404
    inv_snap    = {r['item_code']:max(0,r['total_stock']-r['allocated']) for r in db.execute("SELECT item_code,total_stock,allocated FROM inventory").fetchall()}
    urgency     = calculate_urgency(row)
    urgency_pct = round(min(urgency/MAX_URGENCY*100,100),1)
    allocated, unmet, items_considered = run_lp_knapsack(row, inv_snap, capacity, row['category'])
    for code, qty in allocated.items():
        if qty > 0:
            db.execute("UPDATE inventory SET allocated=allocated+?,last_updated=CURRENT_TIMESTAMP WHERE item_code=?", (qty,code))
    inv_lookup    = {r['item_code']:f"{r['item_name']} ({r['unit']})" for r in db.execute("SELECT item_code,item_name,unit FROM inventory").fetchall()}
    dispatch_lines = [f"{inv_lookup.get(k,k)}: {v}" for k,v in allocated.items() if v > 0]
    unmet_lines    = [f"{inv_lookup.get(k,k)}: {v} units SHORT" for k,v in unmet.items() if v > 0]
    dispatch_str = "\n".join(dispatch_lines) if dispatch_lines else "Nothing dispatched — warehouse has no stock for requested items"
    unmet_str    = "\n".join(unmet_lines) if unmet_lines else "All demands met"
    total_wt     = sum(allocated.get(k,0)*ITEM_CONFIG[k]['weight_kg'] for k in allocated if k in ITEM_CONFIG)
    utilization  = round((total_wt/capacity)*100,1) if capacity > 0 else 0
    transport    = row.get('transport_mode','Lorry')
    admin_note   = (f"Transport: {transport} | Urgency: {urgency} ({urgency_pct}%) | Weight: {total_wt:.1f}kg / {capacity}kg ({utilization}%)\n\n"
                    f"ALGORITHM: Linear Programming (PuLP/CBC) + Knapsack\n\nDISPATCHED:\n{dispatch_str}\n\nSHORTFALL:\n{unmet_str}")
    # FIX 2: Status is 'Dispatched' only if something was actually sent
    actual_status = 'Dispatched' if (total_wt > 0 and dispatch_lines) else 'Not Dispatched'
    db.execute("UPDATE requests SET status=?,admin_notes=?,resolved_at=CURRENT_TIMESTAMP WHERE id=?", (actual_status,admin_note,req_id))
    db.execute('''INSERT INTO dispatch_logs (request_id,shelter_id,username,urgency_score,urgency_pct,capacity_used,utilization_pct,transport_mode,dispatch_detail,unmet_detail)
                  VALUES (?,?,?,?,?,?,?,?,?,?)''',
               (req_id,row['shelter_id'],row['username'],urgency,urgency_pct,total_wt,utilization,transport,dispatch_str,unmet_str))
    # FIX 5: Correct tracking message based on actual dispatch result
    if total_wt > 0 and dispatch_lines:
        msg   = f"Dispatch confirmed. {transport} loaded with {total_wt:.0f}kg of supplies. Now departing warehouse."
        utype = 'dispatched'
    else:
        msg   = "Request processed. Warehouse has insufficient stock. Shortfall logged — items will be dispatched when stock is replenished."
        utype = 'update'
    db.execute("INSERT INTO tracking_updates (request_id,shelter_id,update_type,message,location_tag) VALUES (?,?,?,?,?)",
               (req_id,row['shelter_id'],utype,msg,'Command Center'))
    db.commit()
    return jsonify({'status':'success','allocated':allocated,'unmet':unmet,'urgency':urgency,'urgency_pct':urgency_pct,
                    'weight_used':round(total_wt,2),'utilization':utilization,'dispatch_str':dispatch_str,
                    'unmet_str':unmet_str,'name_map':inv_lookup,'items_considered':len(items_considered)})

@app.route('/api/admin/add_tracking', methods=['POST'])
def add_tracking():
    if session.get('role') != 'admin': return jsonify({'error':'Unauthorized'}), 401
    d   = request.json or {}
    msg = (d.get('message') or '').strip()
    req_id = d.get('request_id')
    if not msg:    return jsonify({'status':'error','message':'Message cannot be empty'}), 400
    if not req_id: return jsonify({'status':'error','message':'Request ID required'}), 400
    db  = get_db()
    req = r2d(db.execute("SELECT shelter_id FROM requests WHERE id=?", (req_id,)).fetchone())
    if not req: return jsonify({'error':'Request not found'}), 404
    db.execute("INSERT INTO tracking_updates (request_id,shelter_id,update_type,message,location_tag) VALUES (?,?,?,?,?)",
               (req_id,req['shelter_id'],d.get('update_type','update'),msg,d.get('location_tag','')))
    db.commit()
    return jsonify({'status':'success'})

@app.route('/api/admin/reject_request', methods=['POST'])
def reject_request():
    if session.get('role') != 'admin': return jsonify({'error':'Unauthorized'}), 401
    d = request.json or {}
    db = get_db()
    db.execute("UPDATE requests SET status='Rejected',admin_notes=? WHERE id=?", (d.get('reason','Rejected by admin'),d['request_id']))
    db.commit()
    return jsonify({'status':'success'})

@app.route('/api/admin/delete_request', methods=['POST'])
def delete_request():
    if session.get('role') != 'admin': return jsonify({'error':'Unauthorized'}), 401
    db = get_db()
    db.execute("DELETE FROM requests WHERE id=?", (request.json['request_id'],))
    db.commit()
    return jsonify({'status':'success'})

@app.route('/api/admin/reset_allocated', methods=['POST'])
def reset_allocated():
    if session.get('role') != 'admin': return jsonify({'error':'Unauthorized'}), 401
    db = get_db()
    db.execute("UPDATE inventory SET allocated=0, last_updated=CURRENT_TIMESTAMP")
    db.commit()
    return jsonify({'status':'success'})

@app.route('/api/admin/low_stock_alerts')
def low_stock_alerts():
    if session.get('role') != 'admin': return jsonify({'error':'Unauthorized'}), 401
    db = get_db(); rows = r2l(db.execute("SELECT * FROM inventory WHERE total_stock > 0").fetchall()); alerts = []
    for r in rows:
        avail = r['total_stock']-r['allocated']; pct = (avail/r['total_stock']*100) if r['total_stock']>0 else 0
        if avail == 0: alerts.append({'item_name':r['item_name'],'category':r['category'],'item_code':r['item_code'],'level':'OUT','available':0,'pct':0})
        elif pct < 15: alerts.append({'item_name':r['item_name'],'category':r['category'],'item_code':r['item_code'],'level':'CRITICAL','available':avail,'pct':round(pct,1)})
        elif pct < 30: alerts.append({'item_name':r['item_name'],'category':r['category'],'item_code':r['item_code'],'level':'LOW','available':avail,'pct':round(pct,1)})
    return jsonify(sorted(alerts, key=lambda x: x['pct']))

@app.route('/api/admin/export_report/<int:req_id>')
def export_report(req_id):
    if session.get('role') != 'admin': return jsonify({'error':'Unauthorized'}), 401
    db  = get_db()
    req = r2d(db.execute("SELECT r.*,s.name AS shelter_name,s.category,s.district,s.state,s.village,s.phone AS shelter_phone,s.email AS shelter_email FROM requests r JOIN shelters s ON r.shelter_id=s.id WHERE r.id=?", (req_id,)).fetchone())
    if not req: return jsonify({'error':'Not found'}), 404
    return jsonify({'request':req,'dispatch_log':r2d(db.execute("SELECT * FROM dispatch_logs WHERE request_id=? ORDER BY id DESC LIMIT 1",(req_id,)).fetchone()),'tracking':r2l(db.execute("SELECT * FROM tracking_updates WHERE request_id=? ORDER BY created_at ASC",(req_id,)).fetchall())})

@app.route('/api/admin/send_email', methods=['POST'])
def send_email():
    if session.get('role') != 'admin': return jsonify({'error':'Unauthorized'}), 401
    d = request.json or {}
    req_id   = d.get('request_id')
    to_email = (d.get('to_email') or '').strip()
    subject  = (d.get('subject') or 'RescueOps — Relief Update').strip()
    body     = (d.get('body') or '').strip()
    if not to_email: return jsonify({'status':'error','message':'Recipient email required'}), 400
    if not body:     return jsonify({'status':'error','message':'Email body required'}), 400
    # req_id is optional — used for tracking log only
    db  = get_db()
    req = r2d(db.execute("SELECT shelter_id FROM requests WHERE id=?", (req_id,)).fetchone()) if req_id else None
    # Log as tracking update only if request exists
    if req_id and req:
        db.execute("INSERT INTO tracking_updates (request_id,shelter_id,update_type,message,location_tag) VALUES (?,?,?,?,?)",
                   (req_id,req['shelter_id'],'email',f"[Email to {to_email}] {body[:200]}{'...' if len(body)>200 else ''}","Email Notification"))
        db.commit()
    if EMAIL_PASSWORD:
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject; msg['From'] = f'RescueOps <{EMAIL_SENDER}>'; msg['To'] = to_email
            html = f"""<html><body style="font-family:system-ui,sans-serif;max-width:600px;margin:auto;padding:20px;">
              <div style="background:#dc2626;padding:20px;border-radius:12px 12px 0 0;text-align:center;">
                <h1 style="color:white;margin:0;font-size:22px;">🚨 RescueOps</h1>
                <p style="color:#fecaca;margin:4px 0 0;font-size:12px;">Disaster Relief Coordination System</p>
              </div>
              <div style="background:#f8fafc;border:1px solid #e2e8f0;border-top:none;padding:24px;border-radius:0 0 12px 12px;">
                <h2 style="color:#1e293b;margin:0 0 16px;">{subject}</h2>
                <div style="background:white;border:1px solid #e2e8f0;border-radius:8px;padding:16px;white-space:pre-wrap;font-size:14px;color:#374151;">{body}</div>
                <p style="margin:16px 0 4px;font-size:12px;color:#94a3b8;">Request ID: #{req_id} · RescueOps Automated Notification</p>
                <p style="font-size:12px;color:#94a3b8;">From: {EMAIL_SENDER}</p>
              </div></body></html>"""
            msg.attach(MIMEText(body,'plain')); msg.attach(MIMEText(html,'html'))
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls(); server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.sendmail(EMAIL_SENDER, to_email, msg.as_string())
            return jsonify({'status':'success','message':f'Email sent to {to_email}','sent':True})
        except Exception as e:
            return jsonify({'status':'partial','message':f'Logged but could not send: {str(e)}','sent':False})
    return jsonify({'status':'partial','message':'Email logged. Set EMAIL_PASSWORD env variable to enable real sending.','sent':False})

@app.route('/api/ping')
def ping():
    if 'user' not in session: return jsonify({'status':'logged_out'}), 401
    db = get_db(); result = {'status':'ok','role':session.get('role')}
    if session.get('role') == 'shelter':
        sid = session.get('shelter_id')
        result['dispatched_count'] = db.execute("SELECT COUNT(*) FROM requests WHERE shelter_id=? AND status='Dispatched'",(sid,)).fetchone()[0]
        result['last_tracking_id'] = db.execute("SELECT COALESCE(MAX(id),0) FROM tracking_updates WHERE shelter_id=?",(sid,)).fetchone()[0]
        result['request_count']    = db.execute("SELECT COUNT(*) FROM requests WHERE shelter_id=?",(sid,)).fetchone()[0]
    elif session.get('role') == 'admin':
        result['pending_count']  = db.execute("SELECT COUNT(*) FROM requests WHERE status='Pending'").fetchone()[0]
        result['total_requests'] = db.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    return jsonify(result)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
