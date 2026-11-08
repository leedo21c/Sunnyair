"""METAR/TAF(aviationweather.gov)와 NOTAM(FAA NMS-API)을 받아 wx/latest.json에 저장합니다.
공채 노트 앱의 '기상 · NOTAM' 탭이 이 파일을 읽어요. 실패한 항목은 이전 값을 유지합니다."""
import json, os, sys, time, re, html, http.cookiejar, urllib.request, urllib.error, urllib.parse, datetime

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

def kma(kind, icao):
    """항공기상청 AMO API (IWXXM XML) — AWC에 없는 국내 공항 보완용 (msgText 원문만 사용)"""
    for base in ("https://amoapi.kma.go.kr/amoApi/iwxxm3/", "http://amoapi.kma.go.kr/amoApi/iwxxm3/"):
        try:
            x = get(base + kind + "?icao=" + icao, timeout=20)
            m = re.search(r"<(?:\w+:)?msgText>(.*?)</(?:\w+:)?msgText>", x, re.S)
            if m:
                t = html.unescape(m.group(1)).strip().rstrip("=").strip()
                if t:
                    return " ".join(t.split())
        except Exception as e:
            print("KMA", kind, icao, base[:5], repr(e)[:120])
    return ""

def awc(kind):
    ids = ",".join(AIRPORTS)
    txt = get(f"https://aviationweather.gov/api/data/{kind}?ids={ids}&format=json" + ("&hours=12" if kind == "metar" else ""))
    out = {}
    for item in json.loads(txt or "[]"):
        icao = item.get("icaoId")
        if not icao or icao in out:
            continue
        out[icao] = {"raw": item.get("rawOb") or item.get("rawTAF") or "", "name": item.get("name") or ""}
    return out

# ── FAA NMS-API (NOTAM Management System) ─────────────────────────────
# 엑셀의 Key → FAA_CLIENT_ID, Secret → FAA_CLIENT_SECRET (GitHub Secrets)
# 시험 환경(staging). 운영 승인 후 Secrets/Variables에 NMS_HOST=https://api-nms.aim.faa.gov 로 바꾸면 됨
NMS_HOST = (os.environ.get("NMS_HOST") or "https://api-staging.cgifederal-aim.com").rstrip("/")

def http_err(e):
    try:
        body = e.read().decode("utf-8", "replace")[:300]
    except Exception:
        body = ""
    return f"HTTP {getattr(e, 'code', '?')} {body}".strip()

def nms_token():
    import base64
    cid, sec = os.environ.get("FAA_CLIENT_ID", "").strip(), os.environ.get("FAA_CLIENT_SECRET", "").strip()
    if not cid or not sec:
        raise RuntimeError("FAA 키 없음")
    auth = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    try:
        txt = get(NMS_HOST + "/v1/auth/token", b"grant_type=client_credentials",
                  {"Authorization": "Basic " + auth, "Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    except urllib.error.HTTPError as e:
        raise RuntimeError("토큰 실패 " + http_err(e))
    tok = (json.loads(txt) or {}).get("access_token")
    if not tok:
        raise RuntimeError("토큰 응답에 access_token 없음")
    return tok

def nms_location(tok, loc):
    q = urllib.parse.urlencode({"location": loc})
    try:
        txt = get(NMS_HOST + "/nmsapi/v1/notams?" + q,
                  headers={"Authorization": "Bearer " + tok, "nmsResponseFormat": "GEOJSON", "Accept": "application/json"}, timeout=30)
    except urllib.error.HTTPError as e:
        raise RuntimeError(loc + " " + http_err(e))
    j = json.loads(txt)
    if str(j.get("status", "")).lower() not in ("success", ""):
        raise RuntimeError(loc + " status=" + str(j.get("status")) + " " + json.dumps(j.get("errors"))[:200])
    items, seen = [], set()
    for f in ((j.get("data") or {}).get("geojson") or []):
        core = ((f.get("properties") or {}).get("coreNOTAMData") or {})
        n = core.get("notam") or {}
        raw = ""
        for t in core.get("notamTranslation") or []:
            if t.get("type") == "ICAO" and t.get("formattedText"):
                raw = t["formattedText"].strip(); break
        if not raw:
            for t in core.get("notamTranslation") or []:
                if t.get("simpleText"):
                    raw = t["simpleText"].strip(); break
        if not raw:
            raw = (n.get("text") or "").strip()
        num, ser = (n.get("number") or "").strip(), (n.get("series") or "").strip()
        if ser and not num.startswith(ser):
            num = ser + num
        raw = "\n".join(l.rstrip() for l in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()
        if not raw or (num, raw) in seen:
            continue
        seen.add((num, raw))
        items.append({"num": num, "raw": raw, "start": n.get("effectiveStart") or "", "end": n.get("effectiveEnd") or "",
                      "fir": n.get("affectedFir") or "", "q": n.get("selectionCode") or ""})
    items.sort(key=lambda x: x["num"])
    return items

def nms_all(locs):
    tok = nms_token()
    out, errs = {}, {}
    for loc in locs:
        try:
            out[loc] = nms_location(tok, loc)
        except Exception as e:
            errs[loc] = str(e)[:300]
        time.sleep(0.5)
    return out, errs

ICAO_URLS = ["https://applications.icao.int/dataservices/api/notams-list",
             "https://applications.icao.int/dataservices/api/notams-stored-list"]
NOTAM_EVERY_H = 5.5   # ICAO 무료 100회 절약: 하루 약 3~4회만 NOTAM 조회 (METAR/TAF는 30분마다)

def icao_notams_all():
    """ICAO API Data Service — Stored NOTAMs, 대한민국(KOR) 전체를 1회 호출로 받음"""
    key = os.environ.get("ICAO_API_KEY")
    if not key:
        raise RuntimeError("ICAO API 키 없음")
    errs = []
    for base in ICAO_URLS:
        try:
            txt = get(base + "?" + urllib.parse.urlencode({"api_key": key, "format": "json", "states": "KOR"}), timeout=90)
            j = json.loads(txt)
            rows = j if isinstance(j, list) else (j.get("data") or j.get("notams") or j.get("items") or [])
            if not isinstance(rows, list):
                raise RuntimeError("예상 밖 응답: " + txt[:200])
            out = {}
            for r in rows:
                loc = (r.get("location") or "").strip().upper()
                raw = (r.get("all") or r.get("message") or "").strip()
                if loc and raw:
                    out.setdefault(loc, []).append({"num": r.get("id") or "", "raw": raw,
                                                    "start": r.get("startdate") or "", "end": r.get("enddate") or ""})
            return out, len(rows)
        except Exception as e:
            errs.append(base.rsplit("/", 1)[-1] + ": " + repr(e)[:200])
    raise RuntimeError(" | ".join(errs))

def obs_time(raw, now):
    m = re.search(r"\b(\d{2})(\d{2})(\d{2})Z\b", raw or "")
    if not m:
        return None
    d, h, mi = map(int, m.groups())
    t = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    try:
        t = t.replace(day=d)
    except ValueError:
        return None
    if t > now + datetime.timedelta(hours=12):  # 월이 바뀐 경우 → 지난달
        prev = now.replace(day=1) - datetime.timedelta(days=1)
        try:
            t = prev.replace(day=d, hour=h, minute=mi, second=0, microsecond=0)
        except ValueError:
            return None
    return t

def wait_fresh_metar(met, key="RKSS", tries=7, gap=120):
    for i in range(tries):
        now = datetime.datetime.now(datetime.timezone.utc)
        want = now.replace(minute=0, second=0, microsecond=0)
        if now.minute < 3:          # 정시 직후 3분 안이면 아직 관측 전 → 직전 시간 기준
            want -= datetime.timedelta(hours=1)
        got = obs_time((met.get(key) or {}).get("raw"), now)
        if got and got >= want:
            if i: print(f"METAR {key} 최신 확인 ({got:%H%M}Z), 재시도 {i}회")
            return met
        print(f"METAR {key} 대기 중: 받은 {got and f'{got:%H%M}Z'} / 기대 {want:%H%M}Z → {gap}초 뒤 재시도")
        time.sleep(gap)
        try:
            new = awc("metar")
            for k, v in new.items():
                o = obs_time((met.get(k) or {}).get("raw"), now)
                n = obs_time(v.get("raw"), now)
                if v.get("raw") and (o is None or (n and n >= o)):
                    met[k] = v
        except Exception as e:
            print("METAR 재시도 실패", e)
    return met

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
    # 정시 METAR는 관측 후 5~10분 뒤에야 aviationweather.gov에 올라옴.
    # :00/:30 직후에 실행되면 직전 시간 METAR만 받아서 최대 1시간 30분까지 묵을 수 있으므로,
    # RKSS 최신 정시 관측이 아직 없으면 2분 간격으로 최대 14분 더 기다렸다가 다시 받는다.
    met = wait_fresh_metar(met)
    try:
        taf = awc("taf")
    except Exception as e:
        print("TAF 실패", e); taf = {}
    icao_all, notam_err, per_err = None, None, {}
    data["notam_checked"] = old.get("notam_checked", "")
    data["notam_updated"] = old.get("notam_updated", "")
    data["notam_source"] = old.get("notam_source", "")
    if os.environ.get("FAA_CLIENT_ID"):
        # FAA NMS-API: 30분마다 지점별 조회 (13회)
        data["notam_checked"] = data["updated"]
        try:
            icao_all, per_err = nms_all(AIRPORTS + FIRS)
            if len(per_err) == len(AIRPORTS + FIRS):
                icao_all, notam_err = None, "NMS: " + next(iter(per_err.values()))
            else:
                data["notam_updated"] = data["updated"]
                data["notam_source"] = "FAA NMS" + (" (시험)" if "staging" in NMS_HOST else "")
            print("NMS", {k: len(v) for k, v in (icao_all or {}).items()}, "오류", per_err)
        except Exception as e:
            notam_err = str(e)[:400]
            print("NMS 실패", notam_err)
    elif os.environ.get("ICAO_API_KEY"):
        last = old.get("notam_checked")
        due = True
        if last and not os.environ.get("FORCE_NOTAM"):
            try:
                due = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(last)).total_seconds() >= NOTAM_EVERY_H * 3600
            except Exception:
                due = True
        if due:
            data["notam_checked"] = data["updated"]
            try:
                icao_all, total = icao_notams_all()
                data["notam_updated"] = data["updated"]
                data["notam_source"] = "ICAO API Data Service"
                print("ICAO NOTAM", total, "건,", len(icao_all), "개 지점")
            except Exception as e:
                notam_err = str(e)[:400]
                print("ICAO NOTAM 실패", notam_err)
    else:
        notam_err = "NOTAM API 키 없음"
    for icao in AIRPORTS + FIRS:
        prev = old.get("airports", {}).get(icao, {})
        if icao not in FIRS:
            if os.environ.get("USE_KMA") and not (met.get(icao) or {}).get("raw"):
                v = kma("metar", icao)
                if v: met[icao] = {"raw": v if v.startswith(("METAR", "SPECI")) else "METAR " + v, "name": ""}
            if os.environ.get("USE_KMA") and not (taf.get(icao) or {}).get("raw"):
                v = kma("taf", icao)
                if v: taf[icao] = {"raw": v if v.startswith("TAF") else "TAF " + v, "name": ""}
        a = {"fir": icao in FIRS, "name": "인천 FIR (공역·항로)" if icao in FIRS else (met.get(icao) or taf.get(icao) or {}).get("name") or prev.get("name", ""),
             "metar": (met.get(icao) or {}).get("raw") or prev.get("metar", ""),
             "taf": (taf.get(icao) or {}).get("raw") or prev.get("taf", "")}
        if icao_all is not None and icao not in per_err:
            a["notams"] = icao_all.get(icao, [])
        else:
            if icao in per_err:
                notam_err = per_err[icao]
            a["notams"] = prev.get("notams", [])
            if notam_err:
                a["notam_error"] = notam_err
        data["airports"][icao] = a
        print(icao, "NOTAM", len(a["notams"]), "METAR", bool(a["metar"]), "TAF", bool(a["taf"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
