USA QUESTO PACCHETTO PER RIPRISTINARE SOLO LA DASHBOARD SUPERENALOTTO SU RENDER.

FILE DA TENERE NEL REPOSITORY GITHUB:
- app.py
- superenalotto_live_dashboard.py
- requirements.txt
- render.yaml
- data/superenalotto_history.csv
- templates/superenalotto.html

IMPOSTAZIONI RENDER:
- Build Command: pip install -r requirements.txt
- Start Command: gunicorn app:app

NOTE:
- La home principale è disponibile su "/"
- La dashboard completa è disponibile su "/superenalotto"
- Questo progetto è separato da EuroMillions