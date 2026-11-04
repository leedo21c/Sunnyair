"""METAR/TAF(aviationweather.gov)와 NOTAM(FAA NOTAM Search)을 받아 wx/latest.json에 저장합니다.
공채 노트 앱의 '기상 · NOTAM' 탭이 이 파일을 읽어요. 실패한 항목은 이전 값을 유지합니다."""
import json, os, sys, time, urllib.request, urllib.parse, datetime

AIRPORTS = ["RKSS", "RKSI", "RKPC", "RKPK", "RKTU", "RKTN", "RKJJ", "RKNY", "RKPU", "RKJB"]
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "wx", "latest.json")
UA = {"User-Agent": "Mozilla/5.0 (study-notes weather fetcher)"}

def get(url, data=None, headers=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
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

def notams(icao):
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
    for icao in AIRPORTS:
        prev = old.get("airports", {}).get(icao, {})
        a = {"name": (met.get(icao) or taf.get(icao) or {}).get("name") or prev.get("name", ""),
             "metar": (met.get(icao) or {}).get("raw") or prev.get("metar", ""),
             "taf": (taf.get(icao) or {}).get("raw") or prev.get("taf", "")}
        try:
            a["notams"] = notams(icao)
        except Exception as e:
            print("NOTAM 실패", icao, e)
            a["notams"] = prev.get("notams", [])
            a["notam_error"] = True
        data["airports"][icao] = a
        print(icao, "NOTAM", len(a["notams"]), "METAR", bool(a["metar"]), "TAF", bool(a["taf"]))
        time.sleep(1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
