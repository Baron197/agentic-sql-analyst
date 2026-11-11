# Demo video script (about 3 minutes)

A screen recording of the live demo at https://arunika-sql.duckdns.org with a voice-over. PT Arunika Niaga and all its data are fictional and synthetic; say so on screen.

**Before recording**
- Browser at 1280 × 800 or larger, zoom 110%, a clean profile with no extensions in view.
- The live questions below cost about $0.001 each (`gpt-6-luna`), well under the demo's $0.50 daily cap. Do one dry run first to check the timing.
- Don't read figures from this script: the answers come from the data, and the voice-over below never quotes a number.
- Have the GitHub repo open in a second tab.

| Time | On screen | Voice-over |
|---|---|---|
| 0:00–0:15 | The sign-in page of the live demo. | "Business users ask data questions every day, and an LLM can write the SQL. The problem is trust: did it query the right thing, is it allowed to see that data, and did it make up a number? This is my answer to that." |
| 0:15–0:25 | Point at the fictional-data notice, then click **Try as analyst**. | "This is a fictional Indonesian retailer with synthetic data. I'll sign in as an analyst who can see every region." |
| 0:25–0:50 | Ask: *What was net revenue by sales channel in Q1 2026?* The steps stream in one by one. | "The question goes through a LangGraph agent. You can see each step as it finishes: an input guard, retrieval of the right views and metric definitions, SQL generation, validation, execution, a result check, and the answer." |
| 0:50–1:20 | The answer: scroll over the assumption, the chart, the SQL, the rows, and open **Run details** (tokens, cost, latency). | "It states the assumption it made, shows the SQL it ran and the rows behind the answer. And this is the key guarantee: the model never typed a single number in this answer. It writes a template with slots, and code fills every figure from the query result. Every run records its tokens, cost, and latency." |
| 1:20–1:40 | Ask: *Metode pembayaran apa yang paling sering dipakai pada tahun 2026?* | "It works in Bahasa Indonesia too, with the same pipeline and the same checks." |
| 1:40–2:00 | Ask: *Delete all orders from 2024.* It is refused at once. Then *Tampilkan alamat email semua pelanggan.*, also refused. | "Write requests and personal data are refused by fixed rules before any model call. And even if something got through, the SQL validator, a read-only transaction, and a read-only database role each block writes on their own. Tests switch off two of the three and show the third still holds." |
| 2:00–2:25 | Sign out, click **Try as manager**, ask: *How many orders did each store get in September 2026?* Point at the store names: Jabodetabek only. | "Now a regional manager for Jakarta. Same question style, but Postgres row-level security only returns their region's rows. The scope is signed per transaction, so even hand-written SQL can't see other regions." |
| 2:25–2:55 | Open the **Evaluation** page: the agent vs baseline table and the findings. | "I built the evaluation before the agent: a 60-question held-out test set, three repeats, against a single-prompt baseline. Honest result: on this small schema the agent isn't more accurate than the baseline. What it adds is that none of its numbers need checking by hand. I publish the null and negative results too, like a critic step that made things worse." |
| 2:55–3:15 | Switch to the GitHub tab: the README, then `docs/ARCHITECTURE.md`. | "Everything is on GitHub: the architecture, the security design with a threat-to-test table, every evaluation result file, and the deployment on AWS with a daily spending cap and a kill switch. Thanks for watching." |

**After recording**
- Trim pauses while answers stream; keep at least one stream in real time so viewers see it is live.
- Add captions; many people watch muted.
- Upload (YouTube unlisted or LinkedIn native), then link it from the README's top section.
