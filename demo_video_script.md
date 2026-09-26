# POLARIS — 2:50 Demo Video Script
### Message flow + 4 key system beats + explicit novelty-vs-existing-systems framing

**Total runtime target: ~2:50** 

**Before recording**: Open the Onshore Command Center dashboard, let the MapLibre globe render completely, and ensure the WebSocket connection is established so live vessel data is ticking.

**Design principle for this cut**: Judges are scoring "what's new here." We explicitly admit that basic CNN image detection is standard, which builds absolute credibility when we hit them with the actual novelty: the KD Surrogate edge deployment and the QUBO QML formulation.

---

## 0:00–0:20 — Hook

**On screen**: Onshore Command Center dashboard, MapLibre globe tracking a vessel heading toward Antarctica. All systems green.

**Say**:
> "Standard maritime routing algorithms like A-star settle for 'good enough' local optimums—which in Antarctica means wasted fuel and dangerous ice encounters. This is POLARIS: a routing platform that guarantees the absolute global optimum by treating navigation as a Quantum Machine Learning problem. But theoretical quantum routing papers already exist. What we're about to show you is how we solved the deployment gap those papers ignore—how to put quantum-level decision-making onto a ship that has no internet."

---

## 0:20–0:50 — The pipeline mechanism, with a structural advantage

**On screen**: UI toggles to show "Ice & Weather Heatmaps." A route generates on screen.

**Say**:
> "Our pipeline ingests live SAR satellite imagery and ERA5 weather data. The ocean is then modeled as a massive, dynamic graph. Here is the first structural difference: standard maritime software recalculates routes by testing paths one by one using classical heuristics. Our MODIP engine translates the entire ocean's constraints into a QUBO formulation. We use Quantum Machine Learning to explore vast combinatorial spaces simultaneously—balancing fuel, sea ice, and ship physics. It doesn't *guess* the best route; it mathematically proves it. That’s a fundamentally different computational model."

---

## 0:50–1:05 — Quick beat: basic CNN Vision (15s)

**How to simulate**: Click a detected iceberg on the map to show its bounding box and confidence score.

**On screen**: Bounding box highlights an iceberg.

**Say**:
> "Extracting these icebergs from raw satellite pixels happens here. This uses a standard Convolutional Neural Network. It’s highly accurate, but we are not claiming basic CNN vision is a novel invention. What comes next is."

---

## 1:05–1:45 — Attack/Challenge: Offline Edge Rerouting — Novelty #1 (40s)

**How to simulate**: Switch to the **Onboard Vessel Panel**. Turn off Wi-Fi or click a "Simulate VSAT Failure" / "Reroute" button. 

**On screen**: The route recalculates instantly in under a second.

**Say**:
> "Here's our first real contribution. You cannot rely on a massive cloud QML pipeline when you are in an Antarctic storm with a broken satellite connection. Standard quantum routing literature stops at the cloud. We don't. We built a Knowledge Distillation—or KD—Surrogate model. It learns the heavy quantum model’s optimal decision boundaries offline, and executes locally on the ship's own hardware. Watch this reroute. That took milliseconds. This isn't a cached route; it is live edge-inference retaining 95% of the quantum model's accuracy. This bridges the gap between theoretical quantum optimization and actual naval deployment."

---

## 1:45–2:15 — Challenge: AI Hallucination — Novelty #2 (30s)

**How to simulate**: Show a route approaching a shallow bathymetry zone, then sharply snapping into a safe deep-water channel.

**On screen**: Route updates, avoiding a red "Shallow Draft" zone.

**Say**:
> "Second contribution. AI hallucinations in maritime routing sink ships. Watch this trajectory. A purely AI-driven routing model might suggest cutting through a shallow strait because the ice looks clear. Our system overrides it instantly. Before any route hits the bridge's navigation screen, it passes through Deterministic Safety Filters—hard-coded physics checks for vessel draft and turning radius. The problem statement asked for AI route optimization. We extended the threat model to include AI failure modes, because mathematical optimums mean nothing if they violate basic naval physics."

---

## 2:15–2:30 — Extra: GNN Fleet Logistics — fast contrast (15s)

**How to simulate**: Zoom out the map to show Maitri Station, Bharati Station, and multiple supply ships.

**On screen**: Network lines connecting ships to stations.

**Say**:
> "And for NCPOR command, our Graph Neural Network doesn’t just route one ship—it instantly predicts cascading supply chain delays across the entire Antarctic fleet."

---

## 2:30–2:50 — Close: the explicit comparison

**On screen**: UI showing the route selection cards (Eco, Safest, Fastest) actively updating via WebSockets.

**Say**:
> "Every decision is synced onshore and onboard via ultra-low-bandwidth WebSockets. To summarize what's actually new here: it's not just a routing algorithm. It’s a QUBO-formulated Quantum search that classical algorithms miss, distilled into a millisecond-fast edge surrogate for disconnected ships, and sandboxed by deterministic physics filters. We didn't just build an AI—we built an information-theoretically sound logistics platform ready for extreme environments."

---

## Delivery notes

- **The hook's promise must pay off explicitly** — if you have to speak faster, do not rush the KD Surrogate section. The KD Surrogate line is the entire answer to "how does this actually work on a ship?"
- **Don't let the CNN beat run long** — its whole purpose is contrast ("this part is standard, watch what isn't"). If you spend 30 seconds talking about how great your CNN is, the judges will think your project is just another standard image classifier. 
- **Rehearse the QUBO line word-for-word at least once** — "translates the entire ocean's constraints into a QUBO formulation" is dense. Hitting it cleanly establishes immense technical authority.
- **If a judge later asks "Do you have a real quantum computer on the ship?"** — the honest, rehearsed answer is "No, and nobody does," and the video already explained that at 1:05 with the KD Surrogate. That line is there specifically so you never get trapped by hardware questions.
