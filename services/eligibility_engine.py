"""Hard eligibility rules live in code, so answers are never invented by an LLM."""


def check_eligibility(profile, schemes):
    results = []
    for s in schemes:
        occ_match = bool(set(s["occupations"]) & set(profile["occupations"]))
        need_match = bool(set(s["needs"]) & set(profile["needs"]))
        if not (occ_match or need_match):
            continue
        income = profile.get("income_lakh")
        if s["max_income_lakh"] is not None and income is not None and income > s["max_income_lakh"]:
            continue
        age = profile.get("age")
        if age is not None:
            if s["min_age"] is not None and age < s["min_age"]:
                continue
            if s["max_age"] is not None and age > s["max_age"]:
                continue
        score = (2 if need_match else 0) + (1 if occ_match else 0)
        results.append((score, s))
    results.sort(key=lambda x: -x[0])
    return [s for _, s in results]
