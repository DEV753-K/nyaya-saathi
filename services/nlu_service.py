"""Turns a free-text message (Hindi / English / Hinglish) into a profile dict.

Default: fast rule-based parser (works offline, no API key).
Optional: set ANTHROPIC_API_KEY to let an LLM extract the profile instead.
"""
import json
import os
import re
import urllib.request

OCCUPATIONS = {
    "farmer": ["farmer", "kisan", "kheti", "khet", "zameen", "acre", "किसान", "खेती", "जमीन", "ज़मीन", "खेत"],
    "student": ["student", "college", "school", "padhai", "scholarship", "छात्र", "पढ़ाई", "कॉलेज", "स्कॉलरशिप", "फीस"],
    "business": ["shop", "dukan", "business", "vyapar", "shopkeeper", "दुकान", "व्यापार", "कारोबार"],
    "artisan": ["carpenter","barber","tailor","potter","mistri","darzi","sunar","lohar","kumhar","artisan","कारीगर","दर्ज़ी","दर्जी","बढ़ई","नाई","कुम्हार","सुनार","लोहार","मिस्त्री"],
    "vendor": ["thela","rehdi","street vendor","vendor","phal wala","sabzi wala","ठेला","रेहड़ी","फेरीवाला"],
    "widow": ["widow","vidhwa","विधवा"],
    "fisher": ["fisher","fisherman","machhli","machhuara","matsya","मछली","मछुआ","मत्स्य"],
    "labourer": ["labour", "labourer", "mazdoor", "mazdur", "worker", "मज़दूर", "मजदूर", "कामगार"],
}
NEEDS = {
    "health": ["hospital", "health", "ilaaj", "ilaj", "bimar", "bimari", "treatment", "surgery", "medical", "इलाज", "बीमार", "बीमारी", "अस्पताल", "स्वास्थ्य"],
    "house": ["house", "home", "ghar", "makaan", "awas", "kaccha", "घर", "मकान", "आवास"],
    "daughter": ["daughter", "beti", "betiyan", "ladki", "girl", "shaadi", "marriage", "बेटी", "बिटिया", "लड़की", "शादी"],
    "loan": ["loan", "lon", "udhaar", "लोन", "कर्ज"],
    "pension": ["pension", "retire", "budhapa", "old age", "पेंशन", "बुढ़ापा", "रिटायर"],
    "education": ["scholarship", "fees", "padhai", "study", "स्कॉलरशिप", "पढ़ाई", "फीस"],
    "insurance": ["insurance","bima","accident","बीमा","दुर्घटना"],
    "cooking": ["gas","lpg","cylinder","chulha","ujjwala","गैस","सिलेंडर","चूल्हा"],
    "skill": ["skill","training","tools","toolkit","हुनर","ट्रेनिंग","प्रशिक्षण","औज़ार"],
    "pregnancy": ["pregnant","pregnancy","garbhwati","delivery","गर्भवती","गर्भावस्था","प्रसव"],
    "savings": ["bank account","khata","jan dhan","jandhan","savings","खाता","जन धन","बचत"],
    "women": ["mahila","women","self help group","shg","महिला","स्वयं सहायता"],
    "job": ["naukri","job","rozgar","berozgar","नौकरी","रोज़गार","रोजगार","बेरोजगार"],
    "food": ["ration","anaaj","food","राशन","अनाज"],
    "disability": ["divyang","viklang","disabled","handicap","विकलांग","दिव्यांग","अपंग"],
    "senior": ["bujurg","senior citizen","boorha","बुज़ुर्ग","बुजुर्ग","वरिष्ठ"],
    "irrigation": ["irrigation","sinchai","drip","sprinkler","borewell","सिंचाई","ड्रिप"],
    "self_employment": ["self employment","new business","naya business","startup","start a business","स्वरोजगार","नया व्यवसाय","नया कारोबार"],
    "fisheries": ["fish farming","fisheries","machhli palan","मछली पालन"],
    "farming": ["farm", "kheti", "crop", "fasal", "खेती", "फसल"],
}


def _has(text, words):
    return any(w in text for w in words)


def _rule_based(message):
    t = message.lower()
    profile = {"occupations": [], "needs": [], "income_lakh": None, "age": None, "gender": None}
    for key, words in OCCUPATIONS.items():
        if _has(t, words):
            profile["occupations"].append(key)
    for key, words in NEEDS.items():
        if _has(t, words):
            profile["needs"].append(key)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|लाख)", t)
    if m:
        profile["income_lakh"] = float(m.group(1))
    m = re.search(r"(\d{2})\s*(?:years|year|saal|sal|वर्ष|साल)", t)
    if m:
        profile["age"] = int(m.group(1))
    if _has(t, ["female", "woman", "mahila", "महिला", "aurat", "औरत"]):
        profile["gender"] = "female"
    return profile


def _llm(message):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    prompt = (
        "Extract a JSON profile from this message from an Indian citizen. Return ONLY JSON with keys: "
        "occupations (subset of farmer, student, business, labourer, artisan, vendor), needs (subset of health, house, "
        "daughter, loan, pension, education, farming, insurance, cooking, skill, pregnancy, savings, women, job, food, disability, senior), income_lakh (number or null), age (int or null), "
        "gender (male, female or null).\n\nMessage: " + message
    )
    body = json.dumps({
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            text = json.loads(r.read())["content"][0]["text"]
        text = re.sub(r"```json|```", "", text).strip()
        data = json.loads(text)
        return {
            "occupations": data.get("occupations") or [],
            "needs": data.get("needs") or [],
            "income_lakh": data.get("income_lakh"),
            "age": data.get("age"),
            "gender": data.get("gender"),
        }
    except Exception:
        return None


def parse_message(message):
    return _llm(message) or _rule_based(message)
