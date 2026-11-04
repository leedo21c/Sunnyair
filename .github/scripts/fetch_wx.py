"""METAR/TAF(aviationweather.gov)와 NOTAM(FAA NOTAM Search)을 받아 wx/latest.json에 저장합니다.
공채 노트 앱의 '기상 · NOTAM' 탭이 이 파일을 읽어요. 실패한 항목은 이전 값을 유지합니다."""
import json, os, sys, time, re, html, http.cookiejar, urllib.request, urllib.parse, datetime

AIRPORTS = ["RKSS", "RKSI", "RKNN", "RKNW", "RKPC", "RKPK", "RKTU", "RKTN", "RKJJ", "RKNY", "RKPU", "RKJB"]
FIRS = ["RKRR"]  # 인천 FIR — 공역·항로·MOA NOTAM (METAR/TAF 없음)
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "wx", "latest.json")
UA = {"User-Agent": "Mozilla/5.0 (study-notes weather fetcher)"}

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
      "Accept-Language": "en-US,en;q=0.9"}
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def get(url, data=None, headers=None, timeout=40):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with OPENER.open(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def awc(kind):
    ids = ",".join(AIRPORTS)
    txt = get(f"https://aviationweather.gov/api/data/{kind}?ids={ids}&format=json" + ("&hours=2" if kind == "metar" else ""))
    out = {}
    for item in json.loads(txt or "[]"):
        icao = item.get("icaoId")
        if not icao or icao in out:
            continue
        out[icao] = {"raw": item.get("rawOb") or item.get("rawTAF") or "", "name": item.get("name") or ""}
    return out

FORM = {"searchType": "0", "designatorsForLocation": "", "designatorForAccountable": "", "latDegrees": "", "latMinutes": "0",
        "latSeconds": "0", "longDegrees": "", "longMinutes": "0", "longSeconds": "0", "radius": "10", "sortColumns": "5 false",
        "sortDirection": "true", "designatorForNotamNumberSearch": "", "notamNumber": "", "radiusSearchOnDesignator": "false",
        "radiusSearchDesignator": "", "latitudeDirection": "N", "longitudeDirection": "W", "freeFormText": "", "flightPathText": "",
        "flightPathDivertAirfields": "", "flightPathBuffer": "4", "flightPathIncludeNavaids": "true", "flightPathIncludeArtcc": "false",
        "flightPathIncludeTfr": "true", "flightPathIncludeRegulatory": "false", "flightPathResultsType": "All NOTAMs", "archiveDate": "",
        "archiveDesignator": "", "offset": "0", "notamsOnly": "false", "filters": "", "minRunwayLength": "", "minRunwayWidth": "",
        "runwaySurfaceTypes": "", "predefinedAbraka": "", "predefinedDabra": "", "flightPathAddlBuffer": "", "recaptchaToken": ""}

def notams_dins(icao):
    """FAA DINS(구형 조회) — 국제 ICAO 공항 NOTAM 원문을 <pre> 블록으로 돌려줌"""
    url = ("https://www.notams.faa.gov/dinsQueryWeb/queryRetrievalMapAction.do?reportType=Raw&formatType=ICAO"
           "&retrieveLocId=" + icao + "&actionType=notamRetrievalByICAOs")
    txt = get(url)
    items = []
    for blk in re.findall(r"<PRE>(.*?)</PRE>", txt, re.S | re.I):
        raw = html.unescape(re.sub(r"<[^>]+>", "", blk)).strip()
        if not raw:
            continue
        m = re.search(r"\b([A-Z]\d{4}/\d{2})\b", raw)
        items.append({"num": m.group(1) if m else "", "raw": raw})
    if not items and "No active NOTAMs" not in txt and "NO NOTAMS" not in txt.upper():
        raise RuntimeError("DINS: NOTAM 블록 없음 (" + str(len(txt)) + " bytes)")
    return items

def notams_faa_api(icao):
    """FAA NOTAM API (api.faa.gov 무료 등록) — GitHub Secrets의 FAA_CLIENT_ID / FAA_CLIENT_SECRET 사용"""
    cid, sec = os.environ.get("FAA_CLIENT_ID"), os.environ.get("FAA_CLIENT_SECRET")
    if not cid or not sec:
        raise RuntimeError("FAA API 키 없음")
    items, page = [], 1
    while True:
        q = urllib.parse.urlencode({"icaoLocation": icao, "responseFormat": "geoJson", "pageSize": 200, "pageNum": page})
        j = json.loads(get("https://external-api.faa.gov/notamapi/v1/notams?" + q, headers={"client_id": cid, "client_secret": sec}))
        feats = j.get("items") or []
        for f in feats:
            core = ((f.get("properties") or {}).get("coreNOTAMData") or {})
            n = core.get("notam") or {}
            raw = ""
            for t in core.get("notamTranslation") or []:
                if t.get("type") == "ICAO" and t.get("formattedText"):
                    raw = t["formattedText"].strip(); break
            if not raw:
                raw = (n.get("text") or "").strip()
            if raw:
                items.append({"num": n.get("number") or "", "raw": raw, "start": n.get("effectiveStart") or "", "end": n.get("effectiveEnd") or ""})
        total = int(j.get("totalCount") or 0)
        if not feats or len(items) >= total or page >= 5:
            break
        page += 1
    return items

def notams(icao):
    errs = []
    if os.environ.get("FAA_CLIENT_ID"):
        try:
            return notams_faa_api(icao), None
        except Exception as e:
            errs.append("faa-api: " + repr(e)[:200])
    try:
        return notams_search(icao), None
    except Exception as e:
        errs.append("search: " + repr(e)[:200])
    try:
        return notams_dins(icao), "; ".join(errs)
    except Exception as e:
        errs.append("dins: " + repr(e)[:200])
    raise RuntimeError(" | ".join(errs))

def notams_search(icao):
    try:
        get("https://notams.aim.faa.gov/notamSearch/nsapp.html")
    except Exception:
        pass
    items, offset = [], 0
    while True:
        form = dict(FORM, designatorsForLocation=icao, offset=str(offset))
        txt = get("https://notams.aim.faa.gov/notamSearch/search", urllib.parse.urlencode(form).encode(),
                  {"Content-Type": "application/x-www-form-urlencoded", "Referer": "https://notams.aim.faa.gov/notamSearch/nsapp.html"})
        j = json.loads(txt)
        lst = j.get("notamList") or []
        for n in lst:
            raw = (n.get("icaoMessage") or n.get("traditionalMessage") or "").strip()
            if raw:
                items.append({"num": n.get("notamNumber") or "", "raw": raw, "start": n.get("startDate") or "", "end": n.get("endDate") or ""})
        total = int(j.get("totalNotamCount") or 0)
        offset += len(lst)
        if not lst or offset >= total or offset > 300:
            break
        time.sleep(1)
    return items

def main():
    try:
        old = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        old = {"airports": {}}
    data = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "airports": {}}
    try:
        met = awc("metar")
    except Exception as e:
        print("METAR 실패", e); met = {}
    try:
        taf = awc("taf")
    except Exception as e:
        print("TAF 실패", e); taf = {}
    for icao in AIRPORTS + FIRS:
        prev = old.get("airports", {}).get(icao, {})
        a = {"fir": icao in FIRS, "name": "인천 FIR (공역·항로)" if icao in FIRS else (met.get(icao) or taf.get(icao) or {}).get("name") or prev.get("name", ""),
             "metar": (met.get(icao) or {}).get("raw") or prev.get("metar", ""),
             "taf": (taf.get(icao) or {}).get("raw") or prev.get("taf", "")}
        try:
            a["notams"], note = notams(icao)
            if note:
                a["notam_note"] = note
        except Exception as e:
            print("NOTAM 실패", icao, e)
            a["notams"] = prev.get("notams", [])
            a["notam_error"] = str(e)[:400]
        data["airports"][icao] = a
        print(icao, "NOTAM", len(a["notams"]), "METAR", bool(a["metar"]), "TAF", bool(a["taf"]))
        time.sleep(1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
