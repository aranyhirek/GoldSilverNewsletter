==> Running 'python3 GoldSilver_News_App.py'
HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"Quote not found for symbol: XAUUSD=X"}}}
$XAUUSD=X: possibly delisted; no price data found  (period=1d) (Yahoo error = "No data found, symbol may be delisted")
/opt/render/project/src/GoldSilver_News_App.py:100: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
  now = datetime.datetime.utcnow().strftime("%Y-%m-%d")
=== Gold/Silver Daily Job started ===
Price fetch error: single positional indexer is out-of-bounds
Traceback (most recent call last):
  File "/opt/render/project/src/GoldSilver_News_App.py", line 178, in <module>
    main()
    ~~~~^^
  File "/opt/render/project/src/GoldSilver_News_App.py", line 170, in main
    email_html = build_email_html(prices, insight)
  File "/opt/render/project/src/GoldSilver_News_App.py", line 109, in build_email_html
    <p><b>Arany (XAUUSD):</b> {prices['gold']} USD</p>
                               ~~~~~~^^^^^^^^
TypeError: 'NoneType' object is not subscriptable
❌ Your cronjob failed because of an error: Exited with status 1
