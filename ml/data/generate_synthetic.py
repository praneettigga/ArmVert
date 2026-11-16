"""Generate a labelled SYNTHETIC Indian SMS/WhatsApp dataset.

Templates are written by the team, modelled on scam patterns publicly described by
I4C, RBI, TRAI and bank advisories. Every row is marked source=synthetic, and the
train/val/test split is done by TEMPLATE id so that test messages come from templates
the model never saw. Real-world performance must be measured on the separate
hand-collected set (data/real_testset_template.csv), not on this file.

Usage: python data/generate_synthetic.py --out data/synthetic.csv --per-template 40
"""
from __future__ import annotations

import argparse
import csv
import random
import string
from pathlib import Path

BANKS = [("SBI", "SBIINB", "sbi"), ("HDFC Bank", "HDFCBK", "hdfc"), ("ICICI Bank", "ICICIB", "icici"),
         ("Axis Bank", "AXISBK", "axis"), ("Kotak", "KOTAKB", "kotak"), ("PNB", "PNBSMS", "pnb"),
         ("Bank of Baroda", "BOBTXN", "bob"), ("Canara Bank", "CANBNK", "canara")]
OFFICIAL_BANK_DOMAINS = {"sbi": "sbi.bank.in", "hdfc": "hdfcbank.com", "icici": "icicibank.com", "axis": "axisbank.com",
                         "kotak": "kotak.com", "pnb": "pnb.bank.in", "bob": "bankofbaroda.bank.in", "canara": "canarabank.com"}
APPS = ["PhonePe", "Paytm", "Google Pay", "BHIM"]
NAMES = ["Rahul", "Priya", "Amit", "Sneha", "Vikram", "Anjali", "Rohan", "Pooja", "Arjun", "Kavya", "Imran", "Fatima", "Suresh", "Lakshmi"]
CITIES = ["Delhi", "Mumbai", "Pune", "Bengaluru", "Hyderabad", "Lucknow", "Jaipur", "Chennai", "Kolkata", "Patna"]
RISKY_TLDS = ["xyz", "top", "icu", "click", "live", "shop", "online", "site", "vip", "info", "in", "com", "co"]
SHORTENERS = ["bit.ly", "tinyurl.com", "cutt.ly", "rb.gy", "is.gd", "shorturl.at"]
STORES = ["Amazon", "Flipkart", "Myntra", "Swiggy", "Zomato", "BigBasket", "Meesho"]
PREFIX = ["AX", "VM", "JD", "BZ", "AD", "VK", "TX", "JM", "CP", "QP"]


def rnd_mobile(r: random.Random) -> str:
    n = str(r.choice("6789")) + "".join(r.choice(string.digits) for _ in range(9))
    return r.choice(["", "+91", "+91 "]) + n


def rnd_header(r: random.Random, code: str, kind: str = "T") -> str:
    return f"{r.choice(PREFIX)}-{code}-{kind}"


def rnd_amount(r: random.Random) -> str:
    v = r.choice([r.randint(1, 99) * 10, r.randint(100, 9999), r.randint(10, 99) * 1000, r.randint(1, 25) * 100000])
    return r.choice([f"Rs.{v}", f"Rs {v:,}", f"₹{v:,}", f"INR {v}", f"Rs.{v}.00"])


def scam_url(r: random.Random, brand: str) -> str:
    kind = r.random()
    words = ["kyc", "update", "verify", "secure", "login", "reward", "help", "service", "online", "netbanking", "pay", "claim"]
    if kind < 0.5:
        dom = f"{brand}-{r.choice(words)}" + r.choice(["", "-" + r.choice(words), str(r.randint(1, 99))]) + "." + r.choice(RISKY_TLDS)
        path = r.choice(["", "/login", "/kyc", "/verify.php", "/index.html", "/update?id=" + str(r.randint(1000, 9999))])
        return r.choice(["http://", "https://", ""]) + dom + path
    if kind < 0.8:
        return f"{r.choice(['https://', ''])}{r.choice(SHORTENERS)}/" + "".join(r.choice(string.ascii_letters + string.digits) for _ in range(6))
    if kind < 0.9:
        return f"http://{r.randint(11, 223)}.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}/{r.choice(words)}"
    return "https://" + "".join(r.choice(string.ascii_lowercase) for _ in range(r.randint(5, 9))) + "." + r.choice(RISKY_TLDS) + "/" + r.choice(words)


def fill(t: str, r: random.Random) -> tuple[str, dict]:
    bank, code, brand = r.choice(BANKS)
    ctx = {
        "bank": bank, "app": r.choice(APPS), "name": r.choice(NAMES), "city": r.choice(CITIES), "store": r.choice(STORES),
        "amount": rnd_amount(r), "amount2": rnd_amount(r), "acct": f"XX{r.randint(1000, 9999)}", "otp": str(r.randint(100000, 999999)),
        "phone": rnd_mobile(r).replace(" ", ""), "time": f"{r.randint(7, 11)}:{r.choice(['00', '15', '30', '45'])} PM",
        "date": f"{r.randint(1, 28):02d}-{r.choice(['Nov', 'Dec', 'Jan'])}-26", "hours": str(r.choice([2, 6, 12, 24, 48])),
        "url": scam_url(r, brand), "official": "https://" + OFFICIAL_BANK_DOMAINS[brand], "ref": str(r.randint(10**11, 10**12 - 1)),
        "awb": "".join(r.choice(string.ascii_uppercase) for _ in range(2)) + str(r.randint(10**8, 10**9)),
        "pct": str(r.choice([3, 5, 8, 10, 20, 30])), "short_legit": r.choice(["amzn.in/d/", "fkrt.it/", "myntr.it/", "bit.ly/"]) + "".join(r.choice(string.ascii_letters) for _ in range(6)),
        "veh": f"{r.choice(['DL', 'MH', 'KA', 'UP', 'TS'])}{r.randint(1, 20):02d}{r.choice(string.ascii_uppercase)}{r.choice(string.ascii_uppercase)}{r.randint(1000, 9999)}",
        "code": code, "brand": brand,
    }
    return t.format(**ctx), ctx


# (template_id, lang, category, sender_kind, text). sender_kind: mobile|header|spoof_header|none|contact
SCAM = [
    ("s_kyc1", "en", "bank_kyc", "mobile", "Dear {bank} customer, your account will be blocked today. Update your KYC immediately: {url}"),
    ("s_kyc2", "en", "bank_kyc", "mobile", "{bank}: Your PAN card is not linked. Your netbanking will be suspended within {hours} hours. Click {url} to update."),
    ("s_kyc3", "hinglish", "bank_kyc", "mobile", "Priya grahak, aapka {bank} khata aaj band ho jayega. KYC update karne ke liye turant click kare {url}"),
    ("s_kyc4", "hi", "bank_kyc", "mobile", "प्रिय ग्राहक, आपका {bank} खाता आज बंद हो जाएगा। तुरंत केवाईसी अपडेट करें: {url}"),
    ("s_kyc5", "en", "bank_kyc", "spoof_header", "Your {bank} YONO/NetBanking access is restricted due to incomplete eKYC. Re-verify Aadhaar now {url} or account will be frozen."),
    ("s_pts1", "en", "prize", "mobile", "Dear user, your {bank} reward points worth {amount} expire today. Redeem now: {url}"),
    ("s_pts2", "hinglish", "prize", "mobile", "{bank} reward points {amount} aaj expire ho rahe hai. Abhi redeem kare {url}"),
    ("s_pow1", "en", "utility", "mobile", "Dear consumer, your electricity power will be disconnected tonight at {time} because your previous month bill was not updated. Please contact electricity officer {phone} immediately."),
    ("s_pow2", "hinglish", "utility", "mobile", "Priya upbhokta, aaj raat {time} baje aapki bijli kaat di jayegi kyunki pichle mahine ka bill update nahi hua. Turant bijli adhikari se sampark kare {phone}"),
    ("s_pow3", "hi", "utility", "mobile", "प्रिय उपभोक्ता, आज रात {time} बजे आपकी बिजली काट दी जाएगी। पिछले महीने का बिल अपडेट नहीं है। तुरंत बिजली अधिकारी से संपर्क करें {phone}"),
    ("s_arr1", "en", "impersonation_police", "mobile", "This is Mumbai Cyber Crime Branch. A parcel in your name with illegal drugs and 5 passports was seized by customs. An arrest warrant is issued. Call {phone} now or you will be placed under digital arrest."),
    ("s_arr2", "en", "impersonation_police", "mobile", "TRAI notice: your mobile number will be blocked in 2 hours due to illegal activity and a money laundering case registered with CBI. Press 9 or call {phone}."),
    ("s_arr3", "hinglish", "impersonation_police", "mobile", "Aapke Aadhaar se ek FedEx parcel bheja gaya jisme drugs mile hai. CBI ne case darj kiya hai. Video call par aaye warna arrest warrant jari hoga. {phone}"),
    ("s_arr4", "hi", "impersonation_police", "mobile", "आपके आधार नंबर पर मनी लॉन्ड्रिंग का केस दर्ज है। डिजिटल अरेस्ट से बचने के लिए तुरंत {phone} पर कॉल करें।"),
    ("s_lot1", "en", "prize", "mobile", "Congratulations! You have won {amount} in the KBC lucky draw. To claim your prize contact {phone} or visit {url}"),
    ("s_lot2", "hinglish", "prize", "mobile", "Badhai ho! Aapne {app} lucky draw me {amount} jeete hai. Inaam claim karne ke liye link kholiye {url}"),
    ("s_lot3", "hi", "prize", "mobile", "बधाई हो! आपने लकी ड्रॉ में {amount} का इनाम जीता है। इनाम पाने के लिए {url} पर जाएं।"),
    ("s_job1", "en", "job_task", "mobile", "Hello! We are hiring for part time job. Earn {amount} daily by liking YouTube videos. Work from home, 30 mins a day. WhatsApp {phone}"),
    ("s_job2", "en", "job_task", "contact", "Hi {name}, I am HR from a digital marketing agency. Simple online task: rate hotels on Google and earn Rs 3000 per day. Join our Telegram group {url}"),
    ("s_job3", "hinglish", "job_task", "mobile", "Ghar baithe roz {amount} kamaye! Sirf videos like karne hai. Abhi join kare {url}"),
    ("s_job4", "en", "job_task", "contact", "Congratulations, your task commission is {amount}. To unlock withdrawal complete the prepaid task by depositing {amount2}."),
    ("s_inv1", "en", "investment", "contact", "Join our VIP stock trading group. Guaranteed returns of {pct}% daily on IPO allotment and stock tips. Limited seats: {url}"),
    ("s_inv2", "hinglish", "investment", "mobile", "Crypto me invest kare aur 30 din me paisa double. Guaranteed profit! Join kare {url}"),
    ("s_upi1", "en", "upi", "mobile", "You have received a cashback of {amount} from {app}. Enter your UPI PIN to receive the amount in your account."),
    ("s_upi2", "hinglish", "upi", "contact", "Sir maine galti se {amount} aapko bhej diye. Main collect request bhej raha hu, please approve the request and enter pin to get refund back to me."),
    ("s_upi3", "hi", "upi", "mobile", "आपको {app} से {amount} कैशबैक मिला है। पैसे पाने के लिए अपना पिन डालें।"),
    ("s_otp1", "en", "credentials", "mobile", "Dear customer, to stop the unauthorised transaction of {amount} on your {bank} card, please share the OTP sent to your mobile with our executive."),
    ("s_otp2", "hinglish", "credentials", "mobile", "Main {bank} head office se bol raha hu. Aapka card block hone wala hai, abhi aaye OTP batao to rok dete hai."),
    ("s_otp3", "en", "credentials", "contact", "Hey it's {name}, I accidentally sent my OTP to your number. Can you please send it back to me? It's urgent."),
    ("s_apk1", "en", "malware", "mobile", "Your vehicle {veh} has a pending traffic challan of {amount}. Download RTO Challan.apk to pay before court action: {url}"),
    ("s_apk2", "hinglish", "malware", "contact", "PM Kisan yojana ki agli kist {amount} pending hai. PM Kisan.apk install kare aur apna naam check kare."),
    ("s_apk3", "en", "malware", "spoof_header", "{bank} KYC update is mandatory. Install the {bank} Customer Support apk from {url}/bank-support.apk"),
    ("s_rem1", "en", "remote_access", "mobile", "Your refund of {amount} for the failed {store} order is pending. Install AnyDesk and share the code with our customer care executive to process."),
    ("s_ref1", "en", "refund", "mobile", "Your {store} order refund of {amount} failed. Call customer care {phone} to receive it within {hours} hours."),
    ("s_loan1", "en", "loan", "mobile", "Your instant personal loan of {amount} is pre-approved without documents or CIBIL. Pay processing fee of Rs 999 to get it today: {url}"),
    ("s_loan2", "hinglish", "loan", "mobile", "Bina document {amount} ka loan turant approved. Abhi apply kare {url}"),
    ("s_fam1", "en", "impersonation_family", "contact", "Hi mum, this is my new number, I lost my phone. I need to pay a bill urgently, can you send {amount} to this UPI? Will explain later."),
    ("s_fam2", "hinglish", "impersonation_family", "contact", "Papa mera accident ho gaya hai, hospital me hu. Jaldi {amount} bhejo is number par, mera phone toot gaya."),
    ("s_gov1", "en", "govt_scheme", "mobile", "Free laptop yojana 2026: students can register for a free laptop under PM scheme. Apply now {url}"),
    ("s_gov2", "hinglish", "govt_scheme", "mobile", "Muft recharge yojana! Sabhi users ko 3 mahine ka free recharge. Abhi claim kare {url}"),
    ("s_cour1", "en", "delivery", "mobile", "IndiaPost: your package {awb} could not be delivered due to incomplete address. Update within {hours} hours: {url}"),
    ("s_cour2", "en", "delivery", "spoof_header", "Your shipment is on hold at our warehouse. Pay a redelivery fee of Rs 25 here: {url}"),
    ("s_tax1", "en", "govt_scheme", "mobile", "Income Tax Department: you are eligible for a tax refund of {amount}. Submit your bank details at {url} to receive it."),
    ("s_sim1", "en", "telecom", "mobile", "Dear user, your SIM KYC is incomplete and your number will be deactivated within {hours} hours. Call {phone} to verify."),
]

LEGIT = [
    ("l_otp1", "en", "otp", "header", "{otp} is your OTP for transaction of {amount} at {store}. Valid for 10 mins. Do not share this OTP with anyone. - {bank}"),
    ("l_otp2", "en", "otp", "header", "Your {bank} NetBanking OTP is {otp}. Never share your OTP, PIN or password with anyone. {bank} will never ask for it."),
    ("l_otp3", "hi", "otp", "header", "{otp} आपका OTP है। इसे किसी के साथ साझा न करें। - {bank}"),
    ("l_otp4", "en", "otp", "header", "Use {otp} to log in to your {store} account. Do not share it with anyone, including {store} staff."),
    ("l_dr1", "en", "transaction", "header", "{amount} debited from A/c {acct} on {date} to VPA merchant@ybl. UPI Ref {ref}. If not done by you, call the number on the back of your card. - {bank}"),
    ("l_cr1", "en", "transaction", "header", "Your A/c {acct} is credited with {amount} on {date} by UPI from {name}. Avl bal {amount2}. - {bank}"),
    ("l_cr2", "hi", "transaction", "header", "आपके खाते {acct} में {date} को {amount} जमा किए गए हैं। - {bank}"),
    ("l_kyc1", "en", "bank_info", "header", "Dear customer, your periodic KYC update is due. Please visit your nearest {bank} branch or update through the official mobile app. Do not share OTP or PIN with anyone."),
    ("l_stmt", "en", "bank_info", "header", "Your {bank} credit card statement for Nov is ready. Total due {amount}, due date {date}. Pay via the {bank} app or {official}"),
    ("l_emi", "en", "bank_info", "header", "EMI of {amount} for loan {acct} will be debited on {date}. Please maintain sufficient balance. - {bank}"),
    ("l_del1", "en", "delivery", "header", "Your {store} order is out for delivery today. Delivery OTP: {otp}. Track: {short_legit}"),
    ("l_del2", "en", "delivery", "header", "Delivered: your {store} package was delivered at {time}. Rate your experience in the app."),
    ("l_del3", "hinglish", "delivery", "contact", "Sir main {store} delivery boy, aapke ghar ke bahar hu, gate khol dijiye"),
    ("l_rch", "en", "telecom", "header", "Recharge of Rs 299 successful on {date}. Validity 28 days, 1.5GB/day. Thank you for choosing us."),
    ("l_bill", "en", "utility", "header", "Your electricity bill of {amount} for Oct is generated. Due date {date}. Pay online at the official board website or app. Ignore if already paid."),
    ("l_bill2", "hinglish", "utility", "header", "Aapka bijli bill {amount} generate ho gaya hai. Antim tithi {date}. Kripya samay par bhugtan kare."),
    ("l_appt", "en", "health", "header", "Your appointment with Dr. Sharma is confirmed for {date} at {time}. Reply C to cancel. - {city} Clinic"),
    ("l_train", "en", "travel", "header", "PNR {ref}: Train 12951 {city} to Delhi on {date}, Coach B2 Seat 34. Have a safe journey. - IRCTC"),
    ("l_promo1", "en", "promo", "header", "Big Billion Sale is live! Up to 70% off on electronics at {store}. Shop now on the app. T&C apply."),
    ("l_promo2", "en", "promo", "header", "Get {pct}% cashback on your next {app} recharge. Offer valid till {date}. T&C apply."),
    ("l_promo3", "hinglish", "promo", "header", "{store} par mega sale! Har order par flat {pct}% off. Aaj hi shopping kare {short_legit}"),
    ("l_p1", "hinglish", "personal", "contact", "Bhai kal {time} baje milte hai, cricket khelne chalenge?"),
    ("l_p2", "en", "personal", "contact", "Hey {name}, are we still on for dinner tonight? Let me know by 7."),
    ("l_p3", "hinglish", "personal", "contact", "Mummy main ghar pahunch gaya, khana kha liya. Kal call karta hu."),
    ("l_p4", "hi", "personal", "contact", "बेटा, शाम को सब्ज़ी लेते आना। पापा का फ़ोन नहीं लग रहा।"),
    ("l_p5", "en", "personal", "contact", "Sent you {amount} for the movie tickets. Check your {app}."),
    ("l_p6", "hinglish", "personal", "contact", "Yaar notes bhej de kal ke lecture ke, exam {date} ko hai"),
    ("l_p7", "en", "personal", "contact", "Happy birthday {name}! Have an amazing year ahead."),
    ("l_p8", "hinglish", "personal", "contact", "Maine {amount} bhej diye, {app} check kar le. Baaki kal de dunga."),
    ("l_job", "en", "job_info", "header", "Your application for Software Engineer at our company has been received. Our team will contact you via official email. We never charge any fee for hiring."),
    ("l_warn", "en", "bank_info", "header", "{bank} never asks for your OTP, PIN or CVV over call or SMS. Beware of fraudsters. Report fraud at 1930."),
    ("l_upi", "en", "transaction", "header", "You have received {amount} from {name} on {app}. No action is needed. Money is already in your bank account."),
    ("l_req", "en", "transaction", "header", "{name} has requested {amount} on {app}. Approve only if you know this person. Your PIN is needed only to pay, never to receive."),
    ("l_school", "en", "education", "header", "Dear parent, the PTM for class 8 is scheduled on {date} at 10 AM. - {city} Public School"),
    ("l_ins", "en", "insurance", "header", "Your health insurance policy premium of {amount} is due on {date}. Renew via the official app or branch."),
    ("l_gov", "en", "govt_info", "header", "Your Aadhaar was used for authentication on {date} at {time}. If not done by you, lock biometrics on the official UIDAI app. - UIDAI"),
    ("l_cour", "en", "delivery", "header", "Your Speed Post article {awb} has been booked. Track on the India Post app. - India Post"),
    ("l_bank_link", "en", "bank_info", "header", "Your {bank} FD of {amount} matures on {date}. Renew or close via net banking at {official}"),
    ("l_cr3", "en", "transaction", "header", "Dear Customer, INR {amount} credited to your A/c {acct} on {date} towards NEFT from {name}. Total Avail.Bal INR {amount2}. - {bank}"),
    ("l_dr2", "en", "transaction", "header", "Sent {amount} from {bank} A/c {acct} to {name} on {date}. UPI Ref No {ref}. Not you? Call the number on your card or SMS BLOCK."),
    ("l_dr3", "hinglish", "transaction", "header", "{bank}: Aapke khate {acct} se {amount} kate gaye, {date}. Agar aapne nahi kiya to turant bank se sampark kare."),
    ("l_atm", "en", "transaction", "header", "ATM withdrawal of {amount} from A/c {acct} at {city} on {date}. Avl Bal {amount2}. - {bank}"),
    ("l_sal", "en", "transaction", "header", "Salary of {amount} credited to your A/c {acct} on {date}. - {bank}"),
    ("l_gas", "hi", "delivery", "header", "आपका एलपीजी सिलेंडर बुक हो गया है। बुकिंग नंबर {ref}। डिलीवरी जल्द होगी।"),
    ("l_bill3", "hi", "utility", "header", "आपका बिजली बिल {amount} जारी हो गया है। अंतिम तिथि {date}। कृपया समय पर भुगतान करें।"),
    ("l_challan", "en", "challan", "header", "A traffic challan of {amount} has been issued for vehicle {veh}. View and pay only on the official Parivahan e-Challan portal."),
    ("l_rch2", "hinglish", "telecom", "header", "Aapka Rs 239 ka recharge safal raha. Validity 28 din. Dhanyavaad."),
    ("l_del4", "hinglish", "delivery", "contact", "Bhaiya aapka parcel guard ke paas rakh diya hai, OTP {otp} tha"),
    ("l_del5", "hi", "delivery", "header", "आपका {store} ऑर्डर आज डिलीवर होगा। डिलीवरी OTP {otp} केवल डिलीवरी के समय बताएं।"),
    ("l_bank_hi", "hi", "bank_info", "header", "{bank}: बैंक कभी भी OTP, PIN या पासवर्ड नहीं मांगता। धोखाधड़ी की शिकायत 1930 पर करें।"),
]


# Compositional everyday chats (legit), so Hinglish/Hindi text is not mostly scams.
CHAT_PARTS = {
    "hinglish": (["", "Bhai ", "Yaar ", "Arre ", "Mummy ", "Papa ", "Didi ", "Beta ", "Sir ", "Bhaiya "],
                 ["kal", "aaj", "abhi", "shaam ko", "raat ko", "subah", "Sunday ko", "{time} baje"],
                 ["milte hai", "ghar aa raha hu", "office se nikal gaya", "market ja rahi hu", "class hai", "match dekhenge",
                  "khana kha liya", "train pakadni hai", "doctor ke paas jaana hai", "paise bhej diye {app} pe", "{amount} de diye",
                  "bill bhar diya", "recharge kar diya", "notes bhej diye", "cake le aana", "late ho jaunga", "call karna", "parcel aa gaya"],
                 ["", ".", " ok?", " 🙂", " na?", " please", ", reply karna", " jaldi aana"]),
    "hi": (["", "बेटा ", "मम्मी ", "पापा ", "भैया ", "दीदी ", "सर "],
           ["कल", "आज", "अभी", "शाम को", "रात को", "सुबह"],
           ["घर आ रहा हूँ", "बाज़ार जा रही हूँ", "खाना बन गया है", "पैसे भेज दिए हैं", "बिल भर दिया", "दवाई ले आना",
            "स्कूल की छुट्टी है", "ट्रेन लेट है", "मीटिंग है", "फ़ोन कर लेना", "पार्सल आ गया"],
           ["", "।", " ठीक है?", " जल्दी आना"]),
    "en": (["", "Hey ", "Hi ", "Bro ", "Ma ", "Sir "],
           ["tomorrow", "today", "tonight", "in the evening", "at {time}", "on Sunday"],
           ["see you at the station", "I'm leaving office now", "paid the bill", "sent you {amount} on {app}",
            "will be late", "call me when free", "the parcel came", "dinner is ready", "meeting moved", "got the tickets"],
           ["", ".", " ok?", " 👍", " thanks!"]),
}


def chat_rows(n: int, r: random.Random) -> list[dict]:
    rows = []
    for i in range(n):
        lang = r.choice(["hinglish", "hinglish", "hi", "en"])
        a, b, c, d = CHAT_PARTS[lang]
        tpl = f"{r.choice(a)}{r.choice(b)} {r.choice(c)}{r.choice(d)}"
        text, ctx = fill(tpl, r)
        split = "test" if i % 10 == 0 else "val" if i % 10 == 1 else "train"
        rows.append({"text": perturb(text, r), "sender": rnd_mobile(r), "label": 0, "category": "personal", "lang": lang,
                     "template": f"chat_{i % 10}", "split": split, "source": "synthetic"})
    return rows


def sender_for(kind: str, ctx: dict, r: random.Random) -> str:
    if kind == "header":
        return rnd_header(r, ctx["code"] if r.random() < 0.6 else r.choice(["AMAZON", "FLPKRT", "IRCTCS", "UIDAI", "JIOINF", "SWIGGY", "PHONPE"]), r.choice("TSP"))
    if kind == "spoof_header":
        return rnd_header(r, r.choice(["BNKALR", "KYCUPD", "INFOSM", "ALERTS"]), "P") if r.random() < 0.5 else rnd_mobile(r)
    if kind in ("mobile", "contact"):
        return rnd_mobile(r)
    return ""


def perturb(text: str, r: random.Random) -> str:
    """Light, realistic noise: casing, spacing, missing punctuation."""
    if r.random() < 0.15:
        text = text.upper()
    elif r.random() < 0.2:
        text = text.lower()
    if r.random() < 0.2:
        text = text.replace(". ", ".. ").replace(", ", ",")
    if r.random() < 0.1:
        text = text.replace("your", "ur").replace("Your", "Ur")
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/synthetic.csv")
    ap.add_argument("--per-template", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    r = random.Random(a.seed)

    rows = []
    for label, templates in ((1, SCAM), (0, LEGIT)):
        tids = [t[0] for t in templates]
        r2 = random.Random(a.seed + label)
        shuffled = tids[:]
        r2.shuffle(shuffled)
        n = len(shuffled)
        split_of = {tid: ("test" if i < max(2, n // 6) else "val" if i < max(4, n // 6 + n // 8) else "train")
                    for i, tid in enumerate(shuffled)}
        for tid, lang, cat, skind, tpl in templates:
            for _ in range(a.per_template):
                text, ctx = fill(tpl, r)
                rows.append({"text": perturb(text, r), "sender": sender_for(skind, ctx, r), "label": label,
                             "category": cat, "lang": lang, "template": tid, "split": split_of[tid], "source": "synthetic"})
    rows += chat_rows(a.per_template * 15, r)
    r.shuffle(rows)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(f"wrote {len(rows)} rows to {out}")
    print("split x label:", dict(Counter((x['split'], x['label']) for x in rows)))


if __name__ == "__main__":
    main()
