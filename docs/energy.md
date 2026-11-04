# Energy for the Atlantean homestead

How much solar, solar thermal and ground-source heat the homestead in
[simple-build.md](simple-build.md) needs. Numbers come from
`tools/energy_budget.py`, which writes `docs/energy_budget.json`. Every
assumption sits at the top of that script, so edit and rerun it for a real
site. These are screening sizes; for a real site, run
[PVWatts](https://pvwatts.nrel.gov/) and a Manual J heat-load calculation.

**The short answer, grid-tied with heat pumps:**

| | New England | Florida |
|---|---|---|
| Electricity per year | 11,400 kWh | 10,100 kWh |
| **Solar panels (430 W)** | **23** (9.5 kW), about 80 m² of ground | **17** (7 kW), about 60 m² |
| With a year-round warm bay | **37** (15.9 kW) | 19 (8 kW) |
| Off-grid instead (December sizing) | 47 panels + 70 kWh battery | 18 panels + 47 kWh |
| Solar thermal collectors, hot water only | 2 (4.3 m²) | 2 (3.1 m²) |
| Ground-source heat pump | 1.5 ton (3.5 with the bay) | 1 ton (2 with the bay) |
| Pond loop on the deep-ring bed | 450 ft, 2 coils (1,050 ft with the bay) | 300 ft, 1 coil |
| Or a slinky trench in a berm core | 300 ft (700 ft with the bay) | 200 ft |

---

## The loads

*A frost-free high tunnel adds about 15,000 kWh of heat a year: 5,000 kWh of
electricity through the heat pump, or 10 more panels. See
[greenhouse.md](greenhouse.md).*

| Load | New England | Florida |
|---|---|---|
| Household: lights, appliances, cooking, well | 5,000 kWh | 5,000 kWh |
| House heating, 150 m², well insulated (heat) | 6,750 kWh | 500 kWh |
| House cooling (heat) | 800 kWh | 9,000 kWh |
| Hot water, family of 4 (heat) | 3,000 kWh | 2,500 kWh |
| Barn: heated troughs and lights, or fans | 900 kWh | 500 kWh |
| Workshop and eOx charging | 1,500 kWh | 1,500 kWh |
| Farm: irrigation pump, spoke drive | 350 kWh | 350 kWh |
| Winter aerator (optional) | 600 kWh | – |

Heat loads go through heat pumps at a COP of 3.5 for heating, 5 for cooling
and 3 for hot water. That's why 10,550 kWh of New England heating, cooling and
hot water costs only about 3,100 kWh of electricity.

---

## Warming the inner ring: only what you cover

Open water loses heat fast, mostly by evaporation. The model uses a lumped
heat-loss coefficient of about 15 W/m²K for open water, 5 under a floating
cover, and 3 under a greenhouse plus a cover. That matches the
industry figure that a covered outdoor pool needs only 30–35 % of the heat of
an uncovered one.

| Option | New England, heat per year | Florida |
|---|---|---|
| Whole inner ring (1,100 m²), open, warmed in spring and autumn | **286,000 kWh**: not practical | 95,000 kWh |
| Whole inner ring under a floating cover, same | 95,000 kWh: not practical | 32,000 kWh |
| **100 m² greenhouse bay, warm all year** | **26,700 kWh** (7,600 kWh of electricity) | **5,200 kWh** |

- **Leave the open rings alone.** You'd need 20–40 times more solar to keep a
  whole open ring warm.
- **Warm a bay.** Close a 100 m² bay of the inner ring under a greenhouse
  beside the courtyard. Run tilapia and greens there all year, and leave the
  rest of the ring to the seasons.
- **In New England the bay is a real cost.** It adds 14 panels and 2 tons of
  heat pump. A summer-only bay, or one half the size, cuts that roughly in
  half.

---

## Solar electricity: on the outer border, not the spoke

- **Where:** a fixed ground mount on the north border of the site.
  - **Tilt and yield:** about 35° in New England, 25° in Florida. Yields are
    about 1,200 kWh per kW of panels per year in Connecticut and 1,450 in
    Florida.
  - **Shading:** panels on the north edge face south across the site, so
    they shade nothing.
  - **The bund:** the windbreak bund made of surplus spoil
    ([simple-build.md](simple-build.md#the-numbers)) gives them a ready
    south-facing slope.
  - **Space:** 23–37 panels need 80–130 m² of ground, a small corner of the
    border.
- **Barn and workshop roofs** can carry part of the array instead, on their
  south-facing arches.
- **Why not the spoke.** The rotating spoke could carry about 22 panels, and
  turning it to follow the sun would add about a quarter more yield. But
  22 panels are a 43 m² sail. In a design gust (about 50 m/s, roughly the
  ASCE 7 wind for Connecticut or central Florida) that's about 77 kN on a
  floating walkway, enough to rip it from its pivot or capsize it. Fixed
  ground mounts don't move, and they shed snow and hurricanes. Put two small
  flat panels on the spoke for its own controls, and nothing more.
- **Goats and panels don't mix.** They climb on them and chew the wiring.
  Sheep can graze under raised panels; goats should stay fenced away from the
  array.
- **Grid-tied is the simple choice.** Going off-grid in New England means
  sizing for December, when panels make about a fifth of their June output.
  That doubles the array to 47 panels and needs a 70 kWh battery. eOx packs
  (4.1 kWh each) could be that battery, but it takes 18 of them. A
  grid-tied system with a couple of eOx packs for outages is far simpler.

---

## Solar thermal: two collectors, or none

- **For hot water:** two flat-plate collectors (about 2.4 m² each) with a
  300 L tank cover about 65 % of New England hot water and 80 % of Florida's.
- **The simpler alternative:** a heat-pump water heater uses about 1,000 kWh
  a year, the output of two more PV panels. Two panels have no glycol to
  change, nothing to freeze, and nothing to boil when you're away.
- **For the warm bay:** solar thermal fits better, because low-temperature
  water heat is what collectors do best. In New England, about 10 collectors
  would carry 40 % of the bay's heat, mostly in spring and autumn. The heat
  pump does the rest.

---

## Ground-source loops: lay them while the crew is digging

A ground-source heat pump moves heat to and from water or soil at a steady
temperature. The usual rules of thumb:
- **Pond loop:** about 300 ft of pipe per ton, in water at least 8–10 ft deep,
  over at least half an acre.
- **Trench loop:** about 125–300 ft of trench per ton.

The 8 ft outer ring meets the pond-loop rule: 1.1 acres of water, with about
0.35 acre deeper than 8 ft.

- **New England: a slinky trench loop in the orchard berm core.**
  - Lay 300–700 ft of slinky loop in a trench 6 ft down while the pond crew is
    building the berm. One lap of the orchard berm is about 720 ft.
  - The trench is dug anyway, so the loop costs little more than the pipe.
  - It takes heat from the soil, not from the fish's winter refuge.
- **Florida: a pond loop in the deep ring.**
  - The load is cooling, so the loop dumps heat into the water.
  - 10,800 kWh over a summer would warm the deep ring by about 1.3 K if it
    lost nothing, and evaporation sheds most of that.
  - 300–600 ft of coil, weighted onto the bed.
- **A pond loop in New England works, but watch the fish.**
  - In winter it would take about 7,000 kWh of heat from the deep ring (about
    26,000 kWh with the warm bay). That equals 1.8–6.8 cm of extra ice over
    the whole ring, which is small.
  - But the heat comes from the 4 °C bottom water where the fish winter.
  - Keep the coils away from the deepest part, or use the trench loop for
    heating and the pond loop only for summer cooling.
- **Make the loop the first thing the crew lays.** It goes in while the
  berm core or the ring bed is open, and adding one later means digging
  again.

---

## Sources

- Pond-loop sizing (about 300 ft of PE pipe per cooling ton; at least ½ acre and 8–10 ft deep):
  [Bryant closed-loop installation guide](https://www.manualslib.com/manual/807430/Bryant-50yew.html?page=55),
  [Young Supply geothermal guide](https://wizard.youngsupply.com/files/59-8932.pdf)
- Horizontal and slinky trench lengths (100–400 ft of trench per ton; slinky shortens it):
  [Horizontal loops](https://www.scribd.com/document/684681410/Horizontal-Loops),
  [HeatSpring loop design](https://blog.heatspring.com/geothermal-loop-design/)
- Solar yield, Connecticut about 1,200 kWh/kW/yr:
  [solar-estimate.org, Hartford](https://solar-estimate.org/residential-solar/news/are-solar-panels-worth-it-in-hartford)
- Covered vs open pool heat demand (a covered pool needs 30–35 % of the heat):
  [Pool & Spa Marketing](https://www.poolspamarketing.com/trade/covers-are-essential-for-a-safe-energy-efficient-swimming-pool/3),
  [EnergyPlus pool model](https://bigladdersoftware.com/epx/docs/23-2/engineering-reference/indoor-swimming-pool.html)
- Florida yield (about 1,450 kWh/kW/yr) is an assumption from typical PVWatts
  results for central Florida. Run PVWatts for the real site.
