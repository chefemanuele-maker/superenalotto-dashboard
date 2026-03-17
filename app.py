from flask import Flask, render_template
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
        data = superenalotto.build_dashboard_data()

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

if __name__ == "__main__":
    app.run(debug=True)
