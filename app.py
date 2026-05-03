from flask import Flask, jsonify, render_template, request
import traceback
import superenalotto_live_dashboard as superenalotto

app = Flask(__name__)

@app.route("/")
def home():
    return """
    <html>
    <head>
        <title>Dashboard SuperEnalotto</title>
        <style>
            body {
                background:#0b0f19;
                color:white;
                font-family:Arial;
                padding:40px;
            }
            a {
                color:#4dd0ff;
                font-size:22px;
                text-decoration:none;
            }
            a:hover {
                text-decoration:underline;
            }
            .box {
                background:#111827;
                padding:30px;
                border-radius:16px;
                max-width:900px;
                box-shadow:0 0 20px rgba(0,0,0,0.3);
            }
            h1 {
                margin-top:0;
            }
            p {
                font-size:18px;
                line-height:1.6;
            }
            pre {
                white-space: pre-wrap;
                background:#111827;
                padding:20px;
                border-radius:12px;
                margin-top:20px;
            }
        </style>
    </head>
    <body>
        <div class="box">
            <h1>Dashboard SuperEnalotto</h1>
            <p>Server attivo correttamente.</p>
            <p>Apri la dashboard completa per visualizzare ultima estrazione, statistiche, best line, linee suggerite e SuperStar consigliato.</p>
            <p><a href="/superenalotto">Apri Dashboard SuperEnalotto</a></p>
        </div>
    </body>
    </html>
    """

@app.route("/superenalotto")
def superenalotto_dashboard():
    try:
        line_count = request.args.get("lines", default=5, type=int)
        if line_count not in [1, 3, 5, 10]:
            line_count = 5
        data = superenalotto.build_dashboard_data(line_count=line_count)

        if not data:
            return "Nessun dato disponibile"

        return render_template("superenalotto.html", **data)

    except Exception:
        err = traceback.format_exc()
        return f"""
        <html>
        <body style="background:#0b0f19;color:white;font-family:Arial;padding:40px;">
            <h1>Errore SuperEnalotto</h1>
            <pre>{err}</pre>
        </body>
        </html>
        """, 500


@app.route("/api/odds")
def api_odds():
    line_count = request.args.get("lines", default=5, type=int)
    if line_count not in [1, 3, 5, 10]:
        line_count = 5
    return jsonify({
        "odds": superenalotto.pack_jackpot_probability(line_count),
        "strategy": superenalotto.budget_strategy(line_count),
    })


@app.route("/api/suggested")
def api_suggested():
    try:
        line_count = request.args.get("lines", default=5, type=int)
        if line_count not in [1, 3, 5, 10]:
            line_count = 5
        data = superenalotto.build_dashboard_data(line_count=line_count)
        return jsonify({
            "ok": True,
            "odds": data["odds"],
            "best_line": data["best_line"],
            "suggested": data["suggested_lines"],
            "quality": data["quality"],
            "strategy": data["strategy"],
            "diversity": data["diversity"],
        })
    except Exception:
        return jsonify({"ok": False, "error": traceback.format_exc()}), 500

if __name__ == "__main__":
    app.run(debug=True)
