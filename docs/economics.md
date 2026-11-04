# Investment and return: the homestead as a product

A cheap hole in the ground is the wrong target. An Atlantean homestead is a
product: someone pays for it to be built, and building it produces things
worth selling. The surplus soil becomes fill, the till's stones become
fieldstone, and the finished site makes electricity, fish, fruit, eggs and
milk every year. This page puts all of that on one ledger.

Numbers come from `tools/homestead_economics.py`, which writes
`docs/homestead_economics.json`. It reads the layouts from
`tools/homestead_numbers.py` ([simple-build.md](simple-build.md)) and the
energy sizes from `tools/energy_budget.py` ([energy.md](energy.md)). Every
price sits at the top of that script. **These are screening figures:** prices
come from vendor and extension sources (listed below), not local quotes. The
buildings and the land are left out.

---

## The soil market decides the earthworks bill

Here is the recommended layout (shallow inner ring, 8 ft outer ring) with the
earthworks netted against what happens to the surplus spoil. The netting
covers the pond crew, surplus handling, and the gravel and sand you buy, less
what the soil and stone sell for.

| What happens to the surplus spoil | NE till, 6 ft slope | NE till, flat | Florida sand |
|---|---|---|---|
| Surplus after raising the island (loose) | 13,000 m³ | 6,700 m³ | 4,000 m³ |
| No market: pay to truck it away ($10/yd³) | $388k | $242k | $159k |
| Keep it as a windbreak bund on site | $224k | $158k | $110k |
| Give it away: haulers take it free | $217k | $155k | $108k |
| **Sell it as common fill ($8/yd³ net, buyer hauls)** | **$81k** | **$85k** | **$66k** |
| **Screen it: sell the stone ($25/t) and screened fill ($12/yd³)** | **$26k** | **$56k** | $69k |

- **The cheapest-hole view gets the slope wrong.** With no market, the 6 ft
  slope adds about $145k. With a fill market it adds almost nothing, and with
  screening it is the cheapest site, because more digging means more product.
- **Deeper rings work the same way.** An 8 ft outer ring makes about
  2,700–4,200 m³ more spoil than a 6 ft ring. That's a cost without a buyer,
  and a product with one.
- **Screening pays where there's stone.** New England till is about 15 %
  cobbles and boulders. Screening the sloped site's surplus yields about
  3,600 t of fieldstone and lets its own stone replace some bought gravel.
  Florida sand has no stone, so there screening only adds cost; sell it as
  fill sand instead.
- **You still buy gravel and sand:** about $36k of processed gravel and
  bedding sand ($28k when the screened stone replaces the causeway base) for the causeway, island drive, courtyard, berm-top paths,
  drains, pipe bedding and footings. Prices are about $50/t delivered for
  gravel and $40/t for sand.

---

## The whole homestead

This is everything except the buildings and the land:
- **Earthworks:** design, permits, earthworks, topsoil handling, surplus
  handling and bought aggregate.
- **Energy:** solar PV ($3.0/W installed, with no federal credit after 2025;
  check state programmes) and the ground-source heat pump with its loop.
- **The farm:** trees, fencing, fish, animals, plants, the pump, and the
  floating spoke.

It assumes the surplus is screened and sold.

| Layout | Site | Build cost | Soil + stone returns | **Net cost** | Yearly value | Payback | NPV, 25 y at 5 % |
|---|---|---|---|---|---|---|---|
| 8 ft outer ring (recommended) | NE 6 ft slope | $388k | $261k | **$127k** | $8.6k | 15 y | −$16k |
| 8 ft outer ring | NE flat | $288k | $131k | **$157k** | $9.6k | 16 y | −$31k |
| 8 ft outer ring | Florida | $215k | $62k | **$153k** | $8.4k | 18 y | −$43k |
| 6 ft outer ring | NE 6 ft slope | $321k | $175k | $146k | $9.2k | 16 y | −$26k |
| 6 ft outer ring | NE flat | $233k | $61k | $172k | $10.1k | 17 y | −$39k |
| Deep ring inside, 2 winter holes | NE flat | $197k | $13k | $184k | $10.3k | 18 y | −$48k |

The yearly value, New England flat, comes to about $9.6k after upkeep:

| Item | Per year |
|---|---|
| Electricity the PV makes, at $0.30/kWh | $3.4k |
| Fruit from a mature orchard of about 70 trees (from year 6) | $4.2k |
| Duck eggs, goats, greens | $4.4k |
| Fish, unfed | $0.4k |
| Upkeep, at 1 % of the build cost | −$2.9k |

- **The farm doesn't pay for the earthworks by itself.** $8–11k a year
  against $130–180k pays back in 14–18 years, and the 25-year NPV comes out
  slightly negative at 5 %.
- **The return is mostly in the soil, the product margin and the land.** The
  table leaves out the value a finished homestead adds to the land. It also
  leaves out what the household stops buying (food, energy, water) and
  resilience. It assumes nothing sells above farm-gate prices.
- **Feeding the fish is the cheapest yearly lever.** The deep ring makes about
  110 lb a year unfed. Fed catfish make about 665 lb, adding about $1.5k a
  year net of feed and cutting payback by about two years.
- **The ground loop pays for itself on day one.** Laid in the berm core
  while the crew is digging, it costs about $1–2k. Drilled bores for the same
  heat pump would cost about $21k more.

---

## As a product

| Spoil | Site | Price at cost + 25 % | Builder's profit, keeping the soil returns | Or price with soil returns passed on |
|---|---|---|---|---|
| Given away | NE 6 ft slope | $398k | $80k | $398k |
| Given away | NE flat | $320k | $64k | $320k |
| **Sold as fill** | **NE 6 ft slope** | $398k | **$216k** | $261k |
| **Sold as fill** | **NE flat** | $320k | **$134k** | $250k |
| Sold as fill | Florida | $239k | $89k | $197k |

The screened case adds the screening cost to the build, so its "price" isn't
comparable; its returns go in the soil table above.

- **Selling the soil is what makes the product work.** It either doubles or
  triples the builder's margin, or it cuts the buyer's price by a fifth to a
  third.
  The business is a homestead builder that's also a fill and stone supplier.
- **Secure buyers before you dig.** Fill is worth something only within a
  short haul.
  - **Who buys it:** developers, town public works, landfill cover, farms
    raising wet fields.
  - **Line it up first:** without a buyer, the same spoil turns into a
    $100k+ cost.
  - **Timing:** a site dug over 4–10 weeks makes 300–1,100 truckloads, so
    line up the buyers' trucks to match.
- **Don't sell the topsoil.** Strip it, stockpile it, and put all of it back
  on the berms; it is the farm. The fill for sale is the subsoil and till
  underneath.
- **Sloped, rocky sites suit this.** A New England hillside that a cheap-hole
  builder would avoid makes the most product. A flat sand lot makes the
  least.

---

## Rules that change the ledger

- **Earth-removal permits.** Many New England towns regulate soil removed off
  site above set volumes, and selling fill commercially may need a town
  earth-removal permit. Check before counting on fill sales.
- **Stormwater.** The site disturbs about 1.8 ha. A construction stormwater
  permit and an erosion plan (the EPA/state construction general permit,
  above 1 acre) are needed, and are included in the design and permit line.
- **Clean fill only.** Buyers and regulators want till and subsoil free of
  debris and contamination. Keep topsoil and organics out of it, and keep
  records of where it came from.
- **Incentives.** The federal residential clean-energy credit (25D) covered
  PV and geothermal through 2025. This model assumes none. State rebates,
  USDA REAP for farms, and net-metering rules can change the energy lines.

---

## Sources

- Fill dirt about $5–25/yd³, more delivered:
  [Hello Gravel, fill dirt 2026](https://hellogravel.com/guides/fill-dirt-cost-per-yard-2026-complete-pricing-guide/)
- Topsoil in CT and MA, $25–60/yd³ delivered:
  [UConn, purchasing topsoil](https://homegarden.cahnr.uconn.edu/factsheets/purchasing-topsoil/),
  [Hello Gravel, Hartford topsoil](https://hellogravel.com/locations/connecticut/hartford-06101/topsoil/)
- Gravel and sand, Northeast:
  [Hello Gravel, sand and gravel 2026](https://hellogravel.com/guides/sand-and-gravel-prices-2026-complete-cost-guide-for-construction-projects-nationwide/)
- New England fieldstone, about $100/t bulk:
  [Stoneyard, Boston Blend wallstone](https://stoneyard.com/product/boston-blend-round-wallstone/),
  [fieldstone cost](https://www.thepricer.org/the-cost-of-fieldstone)
- Pond fish yields (about 300 lb/acre/yr fertile; 400–1,000 lb fed catfish; 30–50 % of standing stock harvestable):
  [Farm Progress](https://www.farmprogress.com/management/successful-ponds-require-good-management),
  [Nebraska pond guide](https://outdoornebraska.gov/wp-content/uploads/2023/03/PMGS_Managing_Bass_Bluegill_Catfish_Pond.pdf),
  [Texas A&M, catfish in farm ponds](https://smith.agrilife.org/files/2018/05/Catfish-in-Farm-Ponds-for-Food-and-Recreation.pdf),
  [Kansas, feeding fish](https://ksoutdoors.gov/Fishing/Special-Fishing-Programs-for-You/Pond-Management-Program/Producing-Fish-and-Wildlife-in-Kansas-Ponds/Fish-Management/Feeding-Fish)
- Not checked here, and worth confirming: hire rates, the screening cost and
  stone fraction of a real till (from test pits), local fill demand, the
  state of 25D and state incentives, and town earth-removal rules.
