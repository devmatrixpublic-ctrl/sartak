"""Walks eight hand-made payment scenarios through the shipped model and prints each score, the alarm line and the reasons.

A teaching and sanity-check tool: it shows HOW the detector decides (which clues add up), not how accurate it is. Uses the reference
feature code (detector/reference/satark_detector.py) and detector/src/main/resources/model.json.

Usage (repo root): python detector/tools/explain_scenarios.py
"""
import json, sys, math
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "detector" / "reference"))
import satark_detector as sd
M = json.load(open(str(Path(__file__).resolve().parents[2] / "detector" / "src" / "main" / "resources" / "model.json")))
WL = set(M["watchlist"]); mean=np.array(M["scaler"]["mean"]); scale=np.array(M["scaler"]["scale"]); coef=np.array(M["logistic"]["coef"]); b=M["logistic"]["intercept"]
COLS=["t_sec","event_type","caller_known","app_package","install_source","payee_id","payee_is_new","amount_inr","payment_type"]
def ev(t,type,**k): return dict(t_sec=t,event_type=type,caller_known=k.get("known"),app_package=k.get("pkg"),install_source=k.get("src"),payee_id=k.get("payee"),payee_is_new=k.get("new"),amount_inr=k.get("amt"),payment_type=k.get("pt"))
def run(name, events, band, med, mad, note):
    df=pd.DataFrame(events,columns=COLS).sort_values("t_sec",kind="stable"); df["session_id"]="s"
    rows,alerts=sd.session_features(df,med,mad,WL)
    thr=M["cohort_thresholds"][band]["threshold"]
    print(f"\n=== {name}\n    {note}\n    user: age band {band}, usual payment ~Rs {med:.0f}; alarm threshold for this band = {thr:.2f}")
    for a in alerts: print(f"    RULE ALARM: {a[1]} at t={a[0]}s  -> HARD intervention")
    for r in rows:
        x=np.array([r[f] for f in M["features"]]); z=(x-mean)/scale; c=z*coef; s=c.sum()+b
        top=sorted([(c[i],M["features"][i]) for i in range(16) if c[i]>0],reverse=True)[:3]
        print(f"    payment at t={r['t']}s: score = {s:+.2f}  ->  {'HARD INTERVENTION' if s>=thr else 'no alarm'}")
        print("      top reasons:", ", ".join(f"{n} (+{v:.2f})" for v,n in top) if s>=thr else "(none)")
        print("      key signals:", {k:round(r[k],2) for k in ("unk_call_active","install_play_during_unk","watchlist_app","new_payee","payee_added_after_unk","log_amt_ratio","ocss_ordered")})
    if not rows and not alerts: print("    nothing to score, no alarm")
AD="com.anydesk.anydeskandroid"
# A: Ramesh, correct order
run("A. Ramesh scam, events in the scam order",[
 ev(0,"CALL_START",known=False),ev(600,"APP_INSTALL",pkg=AD,src="play_store"),ev(1200,"NEW_PAYEE",payee="acct1"),
 ev(1500,"PAYMENT_ATTEMPT",payee="acct1",new=True,amt=160000,pt="P2P")],"60+",800,400,
 "Unknown caller, then remote-access app, then a brand-new payee, then Rs 1.6 lakh.")
# B: scrambled
run("B. Same ingredients, scrambled order",[
 ev(0,"NEW_PAYEE",payee="acct1"),ev(100,"APP_INSTALL",pkg=AD,src="play_store"),ev(900,"CALL_START",known=False),
 ev(1500,"PAYMENT_ATTEMPT",payee="acct1",new=True,amt=160000,pt="P2P")],"60+",800,400,
 "Payee added and app installed BEFORE the call, payment during the call.")
# C: normal
run("C. Normal payment while on a call with a known contact",[
 ev(0,"CALL_START",known=True),ev(300,"PAYMENT_ATTEMPT",payee="landlord",new=False,amt=600,pt="P2P")],"36-59",500,200,
 "Phone call from a saved contact, small payment to a payee the user paid before.")
# D: genuine family emergency
run("D. Genuine family emergency (unknown number, new payee, moderate amount)",[
 ev(0,"CALL_START",known=False),ev(400,"NEW_PAYEE",payee="hospital"),
 ev(700,"PAYMENT_ATTEMPT",payee="hospital",new=True,amt=4000,pt="P2P")],"36-59",500,200,
 "Looks like a scam on the surface; only the amount versus the user's habit differs.")
# E: sideload during call
run("E. Malicious APK installed during an unknown call (no payment yet)",[
 ev(0,"CALL_START",known=False),ev(300,"APP_INSTALL",pkg="apk.unknown.123",src="sideload")],"36-59",500,200,
 "App from outside Google Play while a stranger is on the line.")
# F: long video
run("F. 'Digital arrest' video call from an unknown contact lasting 3 hours",[
 ev(0,"VIDEO_SESSION_START",known=False,pkg="com.whatsapp"),ev(3*3600,"VIDEO_SESSION_END",known=False,pkg="com.whatsapp")],"60+",800,400,
 "No payment at all, but the session is longer than the 2-hour limit.")
# G: call signal missing
run("G. Same scam as A, but the phone could not report call state",[
 ev(600,"APP_INSTALL",pkg=AD,src="play_store"),ev(1200,"NEW_PAYEE",payee="acct1"),
 ev(1500,"PAYMENT_ATTEMPT",payee="acct1",new=True,amt=160000,pt="P2P")],"60+",800,400,
 "No CALL events (permission denied or OEM block). Other clues remain.")
# H: small scam payment
run("H. Same sequence as A, but only Rs 900",[
 ev(0,"CALL_START",known=False),ev(600,"APP_INSTALL",pkg=AD,src="play_store"),ev(1200,"NEW_PAYEE",payee="acct1"),
 ev(1500,"PAYMENT_ATTEMPT",payee="acct1",new=True,amt=900,pt="P2P")],"60+",800,400,
 "Scam order, but an amount close to what this user normally pays.")
