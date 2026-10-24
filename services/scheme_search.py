def search_schemes(query, schemes):
    q = query.lower().strip()
    if not q:
        return schemes
    return [s for s in schemes if q in s["name"].lower() or q in s["benefit_en"].lower()]
