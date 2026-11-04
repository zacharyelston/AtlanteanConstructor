# Building the Atlantean homestead simply

The Atlantean site is a home farm, not an earthworks demo. A family lives on
the centre island in three buildings around a shared courtyard: a house, a barn
for goats and ducks, and a workshop for tools and an eOx. Around the island,
water rings alternate with planted berms. Fish live in the rings, fruit trees
on the berms lean out over the water, ducks work the shallows, and goats graze
the outer ring. A pivot arm floats on the water to tend, pick and clean. The
rings freeze in winter, when nothing is growing, so the arm simply parks.

This document is about building that with as few things as possible that can
break. The numbers come from `tools/homestead_numbers.py` and
`ring_engine/homestead_params.json` on the same terrain engine as the rest of
the repo. They are screening estimates: handbook soil values, assumed hire
rates, and a synthetic site.

It has old precedents. The Pearl River Delta's dike-pond farms grew mulberry
on embankments between fish ponds, fed the leaves to silkworms and the
silkworm droppings to the fish, then dug the pond mud back onto the dikes. FAO
gives dike-to-water area ratios of 1:1, and 4:6 or 3:7 where other feed is
brought in. The Aztec chinampas were planted islands between canals. The
Atlantean version adds a circle, so one pivot can reach everything.

---

## Ten rules for simple and robust

1. **Dig ponds; don't build dams.** Every waterline sits below the lowest
   existing ground around its ring, so no embankment ever holds water back.
   There is nothing to breach or seep, and the site usually stays outside
   dam-safety rules. The terrain engine already designs it this way (level
   water, 0.3 m freeboard).
2. **Let rain fill it, and make the spillway the main structure.** In New
   England the rain on the site is about five times what the rings hold. The
   water problem is overflow, not supply.
3. **Shallow rings, deep winter holes.** Keep the rings 0.9–1.5 m deep so
   they're cheap to dig, easy to plant at the edges and easy to wade. Dig two
   or three 10 ft holes in the fish ring where fish overwinter under the ice.
   That is far cheaper than deepening the whole ring.
4. **Berms are growing land, not spoil heaps.** Build them low (0.9 m) with
   wide flat tops and 3:1 sides you can mow, walk and plant.
5. **Put surplus spoil where it helps.** Raise the house island up to a metre,
   for dry floors and flood safety. Then build a bund on the uphill side that
   turns outside runoff away from the rings.
6. **Strip the topsoil first and put it back on the berms.** Subsoil and till
   don't grow much. Topsoil is the berms' real crop, and it is free if you
   keep it.
7. **Hire the pond crew once.** An excavator and a small dozer are what New
   England pond builders use. They do the job in weeks, not seasons (see
   [the numbers](#the-numbers)). eOx machines maintain the site afterwards.
8. **Motors on land, floats in water.** Nothing powered goes in the water.
   The arm floats on off-the-shelf dock floats and is turned from the island
   end.
9. **Work with the seasons.** Ice is fine: the arm comes ashore in autumn and
   the ducks winter in the barn. Fish winter in the deep holes.
10. **Every stage is useful on its own.** Ponds and berms first, then trees,
    animals and buildings. Add the arm only when tending from a boat gets old.

The New England till turns up about 550 boulders. Those are not waste. They
armour the spillway, line the ring edges, and build steps and dry-stone
walls.

---

## The layout

<!-- radii in homestead_params.json; daylight gaps are 4 m because the banks
     reach further on the high side of a sloped site -->

| Ring | Radius | What it is |
|---|---|---|
| Island | 0–18 m | Three buildings around a courtyard, raised up to 1 m with spoil. The arm turns from a bearing at the island edge. |
| Fish ring | 18–30 m | 1.5 m deep, plus 2 winter holes 10 ft deep and about 12 m across. A shallow safety shelf at the edge, then 2:1 banks below it (the NRCS minimum). |
| Orchard berm | 34–44 m | 0.9 m high, with a 4.9 m flat top. Fruit trees on both edges lean over the water. |
| Plant and duck ring | 48–56 m | 0.9 m deep: emergent plants, summer floating rafts, ducks. |
| Pasture berm | 60–74 m | 0.9 m high, with an 8.9 m flat top, for goats. |
| Uphill bund | outside | Surplus spoil, shaped to turn runoff around the site. |

The whole site is **148 m across (1.72 ha, 4.3 acres)**. A causeway crosses
both rings on the uphill side, with a culvert beneath it, so trucks reach the
island.

**Why these sizes.** Three buildings about 10 m across around a courtyard
about 10 m across need an island of about 18 m radius, against 10 m in the
earlier garden site. The 4 m gaps between rings and berms exist because, on a
slope, a level-water moat's banks reach further out on the high side. The
design check in `terrain_engine.py` refuses a layout where they would run
into a berm.

---

## The numbers

| | NE till, 6 ft slope | NE till, flat | Florida sand, flat |
|---|---|---|---|
| Bank cut (incl. winter holes) | 8,871 m³ | 5,272 m³ | 5,272 m³ |
| Deepest dig | 2.55 m | 1.80 m | 1.80 m |
| Spoil the berms can't take | 6,886 m³ | 1,847 m³ | 300 m³ |
| → island raise / uphill bund | +1.0 m / 5,868 m³ | +1.0 m / 830 m³ | +0.3 m / 0 |
| **Pond crew (excavator + dozer)** | **32 days, $100k** | **20 days, $61k** | **10 days, $33k** |
| Backhoe loader (~90 hp) | 162 days, $243k | – | 53 days, $81k |
| Compact TLB (~45 hp) | 580 days, $605k | – | 193 days, $205k |
| Water held in the rings | 3,859 m³ | 3,859 m³ | 3,859 m³ |
| Rain on the site per year | 20,600 m³ | 20,600 m³ | 23,200 m³ |
| Evaporation from the rings | 2,900 m³ | 2,900 m³ | 5,700 m³ |

8 h working days. Cost is hire with operators, fuel, delivery and a pump.
These are screening rates; get local quotes.

- **Pick the flattest ground you have.** The 6 ft slope adds 68 % to the
  digging and about $39k. It is also where most of the surplus spoil comes
  from, because the high side has to be cut down to level water.
- **The pond crew beats any tractor loader-backhoe.** It is 5× faster and
  2.4× cheaper than the backhoe loader, and digs the 10 ft winter holes
  without fuss.
- **A first try sized the berms to take all the spoil, the way the earlier
  sims do.** It left the berms as sharp ridges with flat tops only 0.5–0.7 m
  wide, useless for trees or goats, and dug 13,249 m³. Low berms at a set
  height, with the surplus spent on the island and the bund, are cheaper and
  give 5–9 m of flat growing ground.

---

## Water: rain, spillway, winter

- **New England: always overflowing.** About 20,600 m³ of rain falls on the
  site each year. The rings hold 3,900 m³ and lose about 2,900 m³ to
  evaporation.
  - The rings never need pumping or topping up.
  - A 100-year, 24-hour storm (about 7.5 in in southern New England) puts
    about 3,300 m³ on the site in a day, nearly the rings' whole volume. The
    spillway has to pass that without washing out.
- **The spillway: wide, shallow and stone-lined, at the low side.**
  - Build it as a grassed channel through undisturbed ground, armoured with
    the boulders from the dig.
  - Avoid pipes and risers as the main outlet: they clog, and that is how
    small ponds fail.
  - The fish ring overflows into the plant ring over a stone weir. The plant
    ring overflows off site through the spillway.
- **Florida: groundwater-fed.** With the water table about 0.9 m down, the
  rings fill from below and their level follows the water table. They need no
  seal, and the level drops in the dry season.
- **The uphill bund keeps outside water out.** On a slope, runoff from the
  land above the site would flow straight into the rings with its silt. The
  bund sends it around.
- **Winter: ice is fine, winterkill is the risk.**
  - Fish die over winter when long ice and snow cover cut off light and air,
    and shallow, weedy ponds are worst.
  - The deep holes are the refuge.
  - Penn State Extension's advice is to keep about 30 % of the ice clear of
    lasting snow, so light still reaches the plants that make oxygen. With
    holes this deep, a small aerator is optional.
- **NRCS reference depths.** Ohio's pond standard asks 8 ft for excavated
  ponds (6 ft if spring-fed). Colorado asks 10 ft over a third of the area for
  cold-water ponds. These rings are shallower on purpose; the holes supply the
  depth.

---

## Soil and sealing

- **New England till usually holds water.** It is clay-rich and dense.
  - The risk is a lens of sand or gravel crossing a ring.
  - Dig 3–4 test pits to 10 ft before anything else, and look for them.
  - If one turns up, cut it out and line that stretch with compacted till
    from elsewhere on site.
- **Compaction.** Place berm and island fill in 6–8 in lifts and track each
  one in with the dozer. It settles less, erodes less, and grows better than
  loose dumped spoil.
- **Seed straight away.** Bare till washes into the rings at the first storm.
  Respread topsoil, seed and mulch each section within days of shaping it.

---

## Buildings on the island

- **Three buildings, one courtyard.** House, barn and workshop face inward;
  the courtyard is the yard, the work area and the arm's base.
- **Choose structures with few seams.**
  - **Geodesic panel domes** look right, but every panel joint is a possible
    leak, and windows and finishes are awkward.
  - **Simpler round choices:** a monolithic concrete or earth-sheltered dome
    for the house, and steel arch (Quonset-type) or hoop buildings for the
    barn and workshop. They are kit-built and snow-shedding, with few joints.
  - Choose deliberately: the house is the one place leaks matter most.
- **Septic and well setbacks are the biggest design risk.**
  - States set minimum distances from a septic field to surface water,
    commonly 50–100 ft. Check yours.
  - An island surrounded by water may have no room for one.
  - The simple answers are composting toilets, or a septic field and a well
    outside the rings, downhill and uphill respectively.
- **Build the causeway and island pad first.** Concrete and delivery trucks
  need a solid road onto the island before the rings are dug around it.

---

## The farm loop

| Part | What lives there | What it gives | Care |
|---|---|---|---|
| Fish ring | New England: yellow perch, bluegill, channel catfish. Florida: catfish, bluegill, and tilapia where the state allows it. | Fish; nutrient-rich water | Stock after the first summer of water, once plankton has established. Check state stocking rules. |
| Orchard berm | Mulberry, persimmon, apples, pears on the water edges | Fruit; dropped fruit feeds the fish | Keep goats out: they strip bark. |
| Plant and duck ring | Watercress, pickerelweed, cattail at the edges; floating rafts of greens in summer | Greens; filtering | Ducks winter in the barn. Ice lets foxes cross. |
| Pasture berm | Goats on rotational paddocks | Milk, meat, brush control | Keep manure back from the water's edge, with a grassed buffer. |
| Pond mud | Dredged from the rings every few years | Fertiliser for the berms | The dike-pond loop. |

- **Aquaponics without tanks.** The ring is the fish tank and the biofilter.
  One small solar pump lifts ring water to drip lines on the orchard berm, and
  it drains back. If the pump stops, nothing dies.
- **The water is a predator barrier.** Foxes and coyotes don't swim to the
  ducks' island in summer. In winter the ice bridges it, so the ducks come in.

---

## The work arm, simply

Each stage is useful on its own. Stop at the stage that does the job.

1. **A boat.** A flat-bottomed punt or kayak with a rope ring around the fish
   ring: feeding, picking overhanging fruit, netting.
2. **A floating spoke.** An aluminium or steel walkway from a pivot bearing at
   the island edge out across the fish ring, onto one or two dock floats (HDPE
   cubes or drums) mid-ring.
   - It cantilevers over the orchard berm's inner edge, so you walk out and
     pick from the trees.
   - You push it round by hand, on a rope.
   - It spans about 26 m. The outer rings are served by boat and the goats.
3. **A powered spoke.** The same spoke, turned by one eOx 3 HP unit at the
   island end, winding a cable laid around the ring like a capstan.
   - The motor and the bus stay on the island, and nothing powered floats.
   - **It sweeps 340° and back** instead of turning full circle, so it never
     meets the causeway. Its cable hangs free, and it needs no slip ring.
   - Tools hang from the spoke: picking trays, a skimmer, later a small suction
     dredge for pond mud.
4. **Winter.** Swing the spoke to the island and lift the floats out, or leave
   them frozen in on purpose. Nothing needs to run until spring.

---

## Build sequence

| When | What |
|---|---|
| Year 0, winter | Choose the flattest spot. Survey it (drone or phone). Dig 3–4 test pits to 10 ft. Talk to the NRCS field office (free pond design help) and the town about wetlands, building and septic permits. |
| Year 1, July–October | Pond crew for about 4–5 weeks (New England, sloped) or 2 weeks (Florida): <ol><li>Strip and stockpile topsoil.</li><li>Build the causeway.</li><li>Dig the rings and winter holes.</li><li>Raise the island pad and the berms in compacted lifts.</li><li>Armour the spillway and the weir.</li><li>Shape the bund.</li><li>Respread topsoil, then seed and mulch.</li></ol> |
| Year 1, winter | The rings fill with rain and snowmelt. |
| Year 2, spring | Plant the orchard berm and the ring edges. Bring the ducks. Fence the pasture. |
| Year 2 | Buildings on the island. Stock fish once the water has had a summer. Bring the goats. |
| Later | The floating spoke, once tending by boat gets old. The eOx for mowing, hauling, mud and regrading. |

---

## How this changes the simulations

- **New layout:** `ring_engine/homestead_params.json`, with berms at a set
  height (`balance.auto_size_berms: false`) instead of sized to take all the
  spoil.
- **New numbers script:** `tools/homestead_numbers.py` reports water held,
  deep-water area, flat crown width, spoil surplus, the water balance, and
  build days and cost for each machine.
- **New baseline machine:** the pond crew (`excavator_dozer` in
  `vehicles/conventional_machines.json`). It digs and pushes at the same time,
  so the job takes the longer task; both machines are paid for.
- **Not modelled yet:**
  - the winter holes as real shapes (they are added as volume only);
  - the causeway;
  - the island raise and the bund as terrain;
  - the spillway, storms and water levels over a year;
  - loads and floats for the spoke.

## Sources

- FAO, dike-pond farming and dike-to-water ratios:
  [fao.org/4/ac241e](https://www.fao.org/4/ac241e/ac241e00.htm),
  [fao.org/4/y1187e](https://www.fao.org/4/y1187e/y1187e09.htm)
- NRCS Conservation Practice Standard 378 (Pond), state versions:
  [Ohio 2018](https://efotg.sc.egov.usda.gov/api/CPSFile/20854/378_OH_CPS_Pond_2018),
  [Colorado 2016](https://efotg.sc.egov.usda.gov/api/CPSFile/3352/378_CO_CPS_Pond_2016),
  [North Carolina 2017](https://efotg.sc.egov.usda.gov/api/CPSFile/23057/378_NC_CPS_Pond_2017),
  [national 2022](https://www.Nrcs.Usda.Gov/sites/default/files/2022-09/Pond_378_NHCP_CPS_2022.pdf)
- Penn State Extension, winterkill in ponds:
  [extension.psu.edu/winterkill-in-ponds](https://extension.psu.edu/winterkill-in-ponds)
- Not separately checked here, and worth confirming locally: the 100-year
  storm depth, septic setbacks, state fish-stocking rules and hire rates.
