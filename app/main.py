import json
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services.eligibility_engine import check_eligibility
from services.nlu_service import parse_message
from services.scheme_search import search_schemes

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "schemes.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Nyaya Saathi")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

with open(DATA_PATH, encoding="utf-8") as f:
    schemes = json.load(f)


class ChatIn(BaseModel):
    message: str
    profile: dict | None = None   # profile remembered from earlier messages
    shown: list[str] = []         # scheme names already shown
    last: list[str] = []          # scheme names shown in the previous reply


def _merge(old, new):
    old = old or {"occupations": [], "needs": [], "income_lakh": None, "age": None, "gender": None}
    return {
        "occupations": sorted(set(old.get("occupations", [])) | set(new["occupations"])),
        "needs": sorted(set(old.get("needs", [])) | set(new["needs"])),
        "income_lakh": new["income_lakh"] if new["income_lakh"] is not None else old.get("income_lakh"),
        "age": new["age"] if new["age"] is not None else old.get("age"),
        "gender": new["gender"] or old.get("gender"),
    }


MORE_WORDS = ["scheme", "yojana", "yojna", "aur", "or ", "more", "other", "batao", "btao", "bataiye",
              "और", "योजना", "बताओ", "बताइए", "दूसरी", "अन्य"]


def _wants_more(text):
    t = text.lower() + " "
    return any(w in t for w in MORE_WORDS)


APPLY_WORDS = ["apply", "application", "aavedan", "avedan", "form", "online", "register", "registration",
               "kaise le", "kaise milega", "link", "आवेदन", "फॉर्म", "ऑनलाइन", "अप्लाई", "रजिस्टर", "लिंक"]
SCHEME_ALIASES = {
    "pmkisan": ["kisan samman", "pm-kisan", "pm kisan", "pmkisan"],
    "pmjay": ["ayushman", "pmjay", "pm-jay", "आयुष्मान"],
    "pmay": ["awas", "pmay", "आवास"],
    "ssy": ["sukanya", "samriddhi", "सुकन्या"],
    "nsp": ["scholarship", "nsp", "स्कॉलरशिप", "छात्रवृत्ति"],
    "mudra": ["mudra", "मुद्रा"],
    "apy": ["atal", "अटल"],
    "ujjwala": ["ujjwala", "उज्ज्वला", "उज्जवला"],
    "pmjjby": ["jeevan jyoti", "jjby", "जीवन ज्योति"],
    "pmsby": ["suraksha bima", "pmsby", "सुरक्षा बीमा"],
    "pmfby": ["fasal bima", "pmfby", "फसल बीमा"],
    "kcc": ["kisan credit", "kcc", "किसान क्रेडिट"],
    "pmvishwakarma": ["vishwakarma", "विश्वकर्मा"],
    "pmmvy": ["matru vandana", "pmmvy", "मातृ वंदना"],
    "ignoaps": ["old age pension", "indira gandhi", "वृद्धावस्था"],
    "pmjdy": ["jan dhan", "jandhan", "जन धन"],
    "standup": ["stand up", "standup", "स्टैंड अप"],
    "nrlm": ["nrlm", "aajeevika", "self help", "आजीविका"],
    "svanidhi": ["svanidhi", "swanidhi", "स्वनिधि"],
    "vidyalaxmi": ["vidyalaxmi", "vidya laxmi", "education loan", "विद्यालक्ष्मी"],
    "ddugky": ["ddu", "gky", "kaushalya", "कौशल्य"],
    "mgnrega": ["mgnrega", "nrega", "manrega", "job card", "मनरेगा"],
    "nfsa": ["ration card", "राशन कार्ड"],
    "udid": ["udid", "disability card", "यूडीआईडी"],
    "ayvvy": ["vay vandana", "वय वंदना"],
    "pmkmy": ["kisan maandhan", "pmkmy", "किसान मानधन"],
    "eshram": ["e-shram", "eshram", "ई-श्रम"],
    "pmksy": ["krishi sinchai", "pmksy", "कृषि सिंचाई"],
    "pmsym": ["shram yogi", "pmsym", "श्रम योगी"],
    "ignwps": ["widow pension", "ignwps", "विधवा पेंशन"],
    "pmmsy": ["matsya sampada", "pmmsy", "मत्स्य संपदा"],
    "pmegp": ["pmegp", "employment generation", "रोजगार सृजन"],
}


def _wants_apply(text):
    t = text.lower()
    return any(w in t for w in APPLY_WORDS)


def _named_schemes(text, all_schemes):
    t = text.lower()
    ids = {sid for sid, words in SCHEME_ALIASES.items() if any(w in t for w in words)}
    return [s for s in all_schemes if s["id"] in ids]


def _has_info(p):
    return bool(p["occupations"] or p["needs"] or p["income_lakh"] is not None or p["age"] is not None or p["gender"])


@app.get("/health")
def health():
    return {"status": "ok", "schemes": len(schemes)}


@app.get("/schemes")
def list_schemes(q: str = ""):
    return search_schemes(q, schemes)


@app.post("/chat")
def chat(body: ChatIn):
    new = parse_message(body.message)
    had_memory = bool(body.profile) and _has_info(_merge(body.profile, {
        "occupations": [], "needs": [], "income_lakh": None, "age": None, "gender": None}))

    # A fresh, clear statement (farmer / daughter / loan / ...) starts a new topic.
    # Only keep old memory for small follow-up details like age or income alone,
    # so "or batao" style replies still work without old topics sticking forever.
    if new["occupations"] or new["needs"]:
        profile = new
    else:
        profile = _merge(body.profile, new)
    matches = check_eligibility(profile, schemes)

    # "How do I apply?" -> show application steps for the named scheme, else the last one shown
    if _wants_apply(body.message):
        target = _named_schemes(body.message, schemes)
        if not target and body.last:
            target = [x for x in schemes if x["name"] in body.last][:2]
        if target:
            return {"profile": profile, "schemes": target, "kind": "apply"}
        if not _has_info(new):
            return {"profile": profile, "schemes": [], "kind": "which_scheme"}

    # Nothing new in this message: user is asking for "more" / "other schemes"
    if not _has_info(new):
        if _wants_more(body.message):
            matched_rest = [m for m in matches if m["name"] not in body.shown]
            names = {m["name"] for m in matched_rest}
            others = [m for m in schemes if m["name"] not in body.shown and m["name"] not in names]
            rest = matched_rest + others
            if rest:
                return {"profile": profile, "schemes": rest[:3], "kind": "more" if had_memory else "all"}
            return {"profile": profile, "schemes": [], "kind": "ask_details"}

    if not matches:
        return {"profile": profile, "schemes": [], "kind": "unknown"}
    return {"profile": profile, "schemes": matches, "kind": "new"}


@app.get("/scheme/{scheme_id}")
def scheme_detail(scheme_id: str):
    for s in schemes:
        if s["id"] == scheme_id:
            return s
    return {"error": "not found"}


class CheckIn(BaseModel):
    scheme_id: str
    answers: dict = {}   # field -> answer text, as typed by the user


def _answer_says_yes(text):
    t = (text or "").strip().lower()
    return any(w in t for w in ["yes", "haan", "han", "ha", "hoon", "hu", "है", "हाँ", "हां", "y"]) and not any(
        w in t for w in ["nahi", "nhi", "no", "नहीं"])


def _extract_number(text):
    import re
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else None


@app.post("/scheme/check")
def scheme_check(body: CheckIn):
    scheme = next((s for s in schemes if s["id"] == body.scheme_id), None)
    if not scheme:
        return {"error": "not found"}

    reasons_fail_en, reasons_fail_hi = [], []
    age_val = None
    income_val = None

    for q in scheme["questions"]:
        ans = body.answers.get(q["field"], "")
        if q["field"] == "age":
            age_val = _extract_number(ans)
            if age_val is not None:
                if scheme["min_age"] is not None and age_val < scheme["min_age"]:
                    reasons_fail_en.append(f"Minimum age for this scheme is {scheme['min_age']}.")
                    reasons_fail_hi.append(f"इस योजना के लिए न्यूनतम उम्र {scheme['min_age']} साल है।")
                if scheme["max_age"] is not None and age_val > scheme["max_age"]:
                    reasons_fail_en.append(f"Maximum age for this scheme is {scheme['max_age']}.")
                    reasons_fail_hi.append(f"इस योजना के लिए अधिकतम उम्र {scheme['max_age']} साल है।")
        elif q["field"] == "income":
            income_val = _extract_number(ans)
            if income_val is not None and scheme["max_income_lakh"] is not None and income_val > scheme["max_income_lakh"]:
                reasons_fail_en.append(f"This scheme is for families earning up to ₹{scheme['max_income_lakh']} lakh a year.")
                reasons_fail_hi.append(f"यह योजना उन परिवारों के लिए है जिनकी सालाना आमदनी ₹{scheme['max_income_lakh']} लाख तक है।")
        elif q["field"] in ("owns_house",):
            if _answer_says_yes(ans):
                reasons_fail_en.append("This scheme is for families who do not already own a pucca house.")
                reasons_fail_hi.append("यह योजना उनके लिए है जिनके पास पहले से पक्का घर नहीं है।")
        elif q["field"] in ("land", "ration_card", "studying", "gender", "bank_account"):
            if ans and not _answer_says_yes(ans):
                reasons_fail_en.append("This scheme usually needs a 'yes' here: " + q["en"])
                reasons_fail_hi.append("आमतौर पर इस योजना में यहाँ 'हाँ' ज़रूरी है: " + q["hi"])

    eligible = not reasons_fail_en
    return {
        "scheme": scheme,
        "eligible": eligible,
        "reasons_en": reasons_fail_en,
        "reasons_hi": reasons_fail_hi,
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
