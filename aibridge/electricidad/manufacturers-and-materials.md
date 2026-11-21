---
title: Manufacturers and materials (brands in Argentina, product lines, published data, how to buy and how to spot counterfeits)
scope: manufacturers and brands of low-voltage electrical materials on the Argentine market (cables, protective devices, SPDs, fuses, contactors, socket outlets and switches, conduit, boxes and enclosures, terminal blocks and lugs, earthing, materials for hazardous areas, emergency lighting, instruments), focused on Argentine manufacturers; objective criteria to choose, buy, file claims and spot counterfeit or non-compliant materials
when_to_use: choosing which brand or line to buy for a job; comparing two products by their technical data; checking whether material the client brought is fit for use; suspecting a cable with less copper, a short coil or a counterfeit MCB; replacing a device in an existing panel; looking for a manufacturer's catalog or data sheet; filing a claim for defective material
related: [README.md, regulations-and-permits.md, iram-standards.md, conductors-and-conduits.md, protection.md, current-ratings-and-devices.md, earthing.md, panels.md, grades-and-circuits.md, buildings.md, special-installations.md, site-safety.md, testing-and-commissioning.md, reviewing-a-panel.md, troubleshooting-common-cases.md]
as_of: 2026-11-15
sources:
  - "Res. SIyC 236/2024 (2024-08-29), Anexo II in the text set by Res. SIyC 26/2025 (BO 2025-02-25): IF-2025-17295098-APN-DNRT#MEC, items 4.1 to 4.7 (electrical installation products and their reference standard), per iram-standards.md (ELEC-IRA-2). The original Anexo II IF-2024-92414137 no longer applies and its numbering does not match"
  - "Disposición DNRT 2/2025 (BO 2025-04-15), Anexo IF-2025-38164600-APN-DNRT#MEC (signed 2025-04-11), implementing Anexo II of Res. SIyC 236/2024: points 1, 2.e, 4.a.iii, 4.1, 5.2.2, 5.2.3 and 5.3"
  - "Prysmian Energía Cables y Sistemas de Argentina S.A.: Ed. 2026 data sheets for Superastic Jet / Flex, Afumex Green 750, Afumex 1000+, Sintenax Valio, Retenax Valio and Retenax Preensamblado (ar.prysmian.com/es/catalogos)"
  - "IRAM: license to use the IRAM mark DC-E-P14-011.2 (Superastic Flex / Jet, IRAM NM 247-3:2003, System 5 ISO/IEC 17067, Res. SIyC 236/24), issued 2025-02-27, next surveillance 2026-02-27, published by Prysmian"
  - "Cimet Optel: technical sheets 09 A2301 (CC/V, IRAM NM 247-3), 10 A2301 (Zerotox 750 V, IRAM 62267) and 07 A2212 (Ecoport CMXCC, IRAM 2164), cimet.com"
  - "Kalop: general catalog (kalop.com.ar/catalogo/kalop-catalogo.pdf, consulted 2026-11-15), back cover 'Fabricado y comercializado en Argentina por Acrópolis Cables S.A., Quilmes' (made and sold in Argentina by Acrópolis Cables S.A., Quilmes)"
  - "Jeluz: Línea Protecciones catalog (Catalogo_protecciones_General.pdf), Canalizaciones (conduit) catalog and distribution item list (Dinbox, Dinbox PRO, Dinbox IP enclosures), downloaded from jeluz.net 2026-11-15"
  - "Schneider Electric Argentina: Catálogo General Retail 2019; data sheets generated on 2026-11-15 for Acti9 iC60N A9F74216 (IRAM certificate DC-E-S26-042.6), Easy9 EZ9F34216 (DC-E-S26-042.4), Easy9 RCCB EZ9R36240 (DC-E-S26-002.20) and busbar comb A9XPH212"
  - "Official sites consulted 2026-11-15: jeluz.net, cambre.com.ar, roker.com.ar, conextube.com, cimet.com, marlew.com.ar, facbsa.com.ar, tacsa.com.ar, kalop.com.ar, zoloda.com.ar, richi.com.ar, delga.com"
  - "Ministerio de Economía y Finanzas de Uruguay: alert/recall of molded-case circuit breakers ComPact NSX, EasyPact CVS/EZC/EZS and PowerPact L (2023-03-13), gub.uy"
  - "Ley 24.240 de Defensa del Consumidor (consumer protection law), arts. 11 and 13 (updated text at argentina.gob.ar/normativa, consulted 2026-11-15)"
  - "IEC 60228 (maximum resistances of class 5 conductors), as reproduced in the Prysmian Ed. 2026 data sheets and the Kalop catalog"
---
# Manufacturers and materials

Which brands are on the Argentine market, what each one makes (and where, when we could confirm it), what technical data it
publishes, and how to choose without falling for counterfeit (*truchos*) materials. Each rule has a stable ID (`ELEC-FAB-n`) so that the agent, a
review or a site report can cite it ("does not comply with ELEC-FAB-7: the coil measured 12 % more resistance than the standard's maximum").

**This is not advertising or a ranking.** There is no "best brand": there are products with a current certificate, published data and
available spare parts, and products without them. Brands are listed in alphabetical order within each category. None appears
because of a commercial recommendation, and a missing brand does not mean it is bad: it means we could not verify it.
When a table gives data from a single brand, it is an **example of how to read a data sheet**, not a preference. There are no prices.

**How origin is reported.** An Argentine brand may make part of its line here and import the rest. In this guide:
- **"Local manufacturing verified"** ("Fabricación local verificada"): a manufacturer's document or a certificate says so (for example "Industria Argentina"
  printed on the cable marking according to the data sheet, or the address of the inspected production plant in an IRAM license).
- **"Local manufacturing declared"** ("Fabricación local declarada"): the company says on its site or in its catalog that it designs and manufactures, without saying which product
  comes from which plant.
- **"Argentine company, local manufacturing not verified"** ("Empresa argentina, fabricación local no verificada"): the company is Argentine, but we found no document that says
  which products it makes here.
- **"Origin not verified"** ("Origen no verificado"): we could confirm neither the company nor the manufacturing.

The real origin of each product is on its label, in the sworn declaration of conformity and in the certificate. When in
doubt, those documents prevail over this guide.

**Limitation of this edition.** Many manufacturer sites could not be read (down, with an expired TLS certificate or
blocking automated access) and the web search budget ran out during the research. That is why several brands
widely used on site remain "not verified". Before citing a brand's data in a project, open the current data sheet
of the exact model.

**Safety first.** Choosing the right material does not replace installing it correctly. Every change in a panel (distribution board, *tablero*) is done dead,
under lockout/tagout (*consignado*) and with absence of voltage verified (see [site-safety.md](site-safety.md)). The agent calculates current, voltage drop,
cross-section and coordination with `gateway electricidad current|drop|size|coordinate|demand|building|earth|tables`,
not from memory.

## Quick reference

| Situation | Rules |
|---|---|
| Is this material legal? How do I verify the certification? | ELEC-FAB-1, ELEC-FAB-2 |
| Where do I buy so I don't end up with counterfeits? | ELEC-FAB-3 |
| Comparing two brands or two lines | ELEC-FAB-4, ELEC-FAB-5 |
| Is it Argentine or imported? | ELEC-FAB-5 |
| What a cable's printing has to say | ELEC-FAB-6 |
| I suspect the cable has less copper | ELEC-FAB-7 |
| I suspect the coil is not the full 100 m | ELEC-FAB-21 |
| Which cable line goes where (conduit, cable tray, buried, LS0H, service connection) | ELEC-FAB-8 |
| Breaking capacity: 3, 4.5, 6 or 10 kA? Icn or Icu? | ELEC-FAB-9 |
| Busbar combs (*peines*), accessories, replacing a device in an assembled panel | ELEC-FAB-10 |
| Choosing an RCD by type and sensitivity in the catalog | ELEC-FAB-11 |
| MCB or RCD suspected of being counterfeit | ELEC-FAB-12 |
| SPDs and voltage protectors | ELEC-FAB-22 |
| Fuses and fuse bases | ELEC-FAB-23 |
| Contactors, motor protection circuit breakers, thermal overload relays | ELEC-FAB-24 |
| Circuit breakers above 63 A (molded case, incoming switches) | ELEC-FAB-25 |
| Socket outlets, modules and mounting frames | ELEC-FAB-13 |
| Light switches | ELEC-FAB-26 |
| Plugs, power strips and extension cords | ELEC-FAB-14 |
| Conduit and boxes | ELEC-FAB-15 |
| Panel enclosures | ELEC-FAB-16 |
| Terminal blocks, ferrules, lugs | ELEC-FAB-27 |
| Insulating tapes | ELEC-FAB-28 |
| Earth rods (*jabalinas*), rod clamps and welding | ELEC-FAB-17 |
| Hazardous areas (explosion-proof) | ELEC-FAB-29 |
| Emergency lighting | ELEC-FAB-18 |
| Instruments (megohmmeter, earth resistance tester, RCD tester) | ELEC-FAB-19 |
| The client brought the material | ELEC-FAB-20 |
| The material turned out defective: warranty, claim, complaint | ELEC-FAB-30 |

## General rules for any material

### ELEC-FAB-1: Only material with a current certificate and conformity marking, and it is verified, not assumed
- **Rule:** all material covered by the technical regulation (cables, MCBs (*térmicas*), RCDs (*diferenciales*), SPDs (*DPS*), circuit breakers and switches,
  isolators (*seccionadores*), socket outlets, plugs, extension cords, conduit, boxes, earth rods and in general materials for installations of
  **50 to 1000 V AC and 75 to 1500 V DC, up to 63 A**, plus all cables with no current limit) must have a
  current certificate and conformity marking. If it does not, it is not installed, whatever the brand.
- **Why:** the mark is the only thing that says a laboratory tested that model (or that batch) and, in scheme 5, that someone
  checks the factory again. A well-known brand does not protect you against a counterfeit of that same brand.
- **How:**
  1. Look on the product or the package for the current conformity marking: the "AR" mark with a double tick and the QR code that
     links to the sworn declaration and the certificate (details of the regime and dates in
     [regulations-and-permits.md](regulations-and-permits.md), ELEC-NOR-14).
  2. Scan the QR and check that the certificate is for **that** model, **that** manufacturer or importer and **that** standard.
  3. If the product has an IRAM mark, the license number has a format like `DC-E-...` (real examples: Prysmian
     Superastic, license **DC-E-P14-011.2**; Schneider Acti9 iC60N, certificate **DC-E-S26-042.6**). The IRAM license says
     that, **after the "Fecha de Próximo Seguimiento" (next surveillance date), it is only valid together with the surveillance record** issued by
     IRAM. In DC-E-P14-011.2 that date was 2026-02-27: as of 2026-11-15 it has passed, so what you need to see is the
     later surveillance record, not just the license.
  4. For MCBs, RCDs, SPDs, manual and LV switches, isolators and cables, the certificate must be
     under scheme **1b or 5** (point 5.2.3 of the annex). Scheme 5 includes type testing and factory surveillance; the
     Prysmian certificate says so ("Sistema 5 ISO/IEC 17067"). Scheme 1b certifies **one batch** by sampling.
- **Verify:**
  - Certificate less than 2 years from its original issue or, after that period, with its **latest surveillance record**
    (without a record a new certificate must be obtained: point 5.2.2).
  - If it is scheme 1b, the batch or customs clearance on the certificate matches the one on the product or the invoice.
  - A certificate issued under the old Res. 169/2018 is no longer valid (it expired in mid-April 2026, ELEC-NOR-14).
  - A product made or imported after 2025-10-01 that carries only the old safety mark is in breach.
- **Don't:** accept as proof a photo of the certificate the seller sends by message; confuse management system
  certifications (ISO 9001, ISO 14001) with product certification: a plant's ISO 9001 does not certify that an
  MCB complies with IEC 60898-1.
- **Source:** Disp. DNRT 2/2025 (BO 2025-04-15), Anexo IF-2025-38164600-APN-DNRT#MEC, implementing Anexo II of
  Res. SIyC 236/2024: points 1 (scope in AC and DC), 2.e (exclusion above 63 A except cables), 5.2.2 (2-year validity and
  surveillance), 5.2.3 (schemes 1b or 5) and 5.3 (marking). IRAM license DC-E-P14-011.2 (validity text, dates and scheme).
  Schneider data sheet A9F74216 (2026-11-15). See also ELEC-NOR-14, ELEC-IRA-4 and ELEC-PRO-22. That scheme 1b is per batch is
  the summary of ISO/IEC 17067: **Not verified in a primary source** (paid standard).

### ELEC-FAB-2: The certificate must match what you have in your hand
- **Rule:** check that four data items match between the product and the certificate: **brand, model or line, standard and
  characteristics** (cross-section and voltage for a cable; In, curve, poles and breaking capacity for an MCB; In, IΔn and type for an
  RCD).
- **Why:** the most common trick is not the product without a mark, but the mark of one model stuck on another: a real
  certificate for a 1.5 mm² cable used to sell a "2.5" one that is not, or the one for a 6 kA line used for a 3 kA line.
- **How:** the Prysmian IRAM certificate, for example, details the product ("cables aislados con PVC para tensiones
  nominales hasta 450/750 V": PVC-insulated cables for rated voltages up to 450/750 V), the models (Superastic Flex and Superastic Jet), the range of cross-sections covered (Flex from 0.5 to
  240 mm², Jet from 0.5 to 6 mm²), the designation (247 NM 02-C5-BWF-B), the standard (IRAM NM 247-3:2003) and the inspected plant.
  Compare those data one by one with the cable's printing.
- **Verify:** the certificate's range includes the cross-section or rating you bought.
- **Don't:** accept a certificate for "the brand" without looking at which products it covers.
- **Source:** IRAM license DC-E-P14-011.2 (fields product, type reference, main characteristics, standard, plant);
  Prysmian Superastic Jet / Flex data sheet Ed. 2026 (printed marking).

### ELEC-FAB-3: Buy from official distributors and ask for the documentation
- **Rule:** buy from electrical supply stores that appear on the manufacturer's distributor list and ask, for
  each lot, for an invoice with brand and model and, if in doubt, the sworn declaration of conformity.
- **Why:** the official distributor buys from the manufacturer or its representative; a reseller without backing may have
  smuggled, second-grade or counterfeit goods. Also, if the product turns out defective, the claim and the replacement
  go through the distributor (ELEC-FAB-30).
- **How:**
  - Several manufacturers publish their network: Jeluz (jeluz.net/pages/distribuidores), Cambre (distribuidores.cambre.com.ar), Kalop
    (kalop.com.ar/distribuidores). For other brands, ask the manufacturer about its channel.
  - When buying online, the listing must show the marking and the technical data.
  - If the appliance comes with a **plug (*ficha*, *enchufe*) that is not the Argentine** IRAM 2073 / IRAM 2063 type (Schuko, American, etc.), the annex
    requires the listing and the product to warn about it. Don't install a universal socket outlet to use it (they are prohibited,
    ELEC-FAB-13): replace the plug with an IRAM one or use a certified adapter with earth (ELEC-IRA-9).
  - Keep the invoices with the job file (see [testing-and-commissioning.md](testing-and-commissioning.md),
    ELEC-MED-11).
- **Verify:** the store appears on the manufacturer's list or can show who it buys from.
- **Don't:** buy MCBs, RCDs or cable "by the kilo" or loose without packaging, at street markets or from listings without
  data; accept "es la misma que la original, viene de la misma fábrica" ("it's the same as the original, it comes from the same factory").
- **Source:** distributor lists published on jeluz.net, cambre.com.ar and kalop.com.ar (consulted 2026-11-15);
  Disp. DNRT 2/2025, Anexo IF-2025-38164600-APN-DNRT#MEC, point 4.a.iii (appliances with plugs not conforming to IRAM 2073 /
  IRAM 2063: label and warning text mandatory). **Not verified in a primary source:** that there is a legal obligation for the
  store to hand the sworn declaration to the buyer; the conformity document must exist and the store can
  request it from its supplier.

### ELEC-FAB-4: Choose by published technical data, not by brand
- **Rule:** to compare two products, compare their data sheets: standard they comply with, rated data, declared tests
  and conditions of use. If a manufacturer does not publish the model's data sheet, that counts against it.
- **Why:** two "16 A" MCBs may differ in breaking capacity (3 kA versus 10 kA), in the standard (IEC 60898-1 or only
  IEC 60947-2), in the energy limiting class and in the cables their terminals accept. Two "2.5" cables may differ in the
  conductor class, in the fire test and in whether they are LS0H or not.
- **How:** the minimum the data sheet must have, and the standard the technical regulation uses to assess it:

  | Material | Reference standard (Res. SIyC 236/2024, Anexo II per Res. SIyC 26/2025) | Minimum data to compare |
  |---|---|---|
  | Cable | IRAM NM 247-3, IRAM 62267, IRAM 2178-1, IRAM 62266 (items 4.3.1 to 4.3.4) | Voltage (450/750 V or 0.6/1 kV), conductor class (IRAM NM 280 / IEC 60228), maximum temperature (70 °C PVC, 90 °C XLPE), fire tests, maximum resistance at 20 °C, current-carrying capacity with its installation condition |
  | MCB (PIA) | IEC 60898-1 (4.5.2) | In, curve, protected poles, Icn in A, energy limiting class, terminal cross-section, tightening torque |
  | RCD | IEC 61008-1 / IEC 61009-1 (4.5.3, 4.5.4) | In, IΔn, type (AC, A, F, B; S if selective), poles, conditional short-circuit current with which upstream protection |
  | SPD | IRAM 2345 / IEC 61643-11 (4.5.14) | Type (1, 2, 3), Uc, Up, In or Iimp, backup protection |
  | Light switch | IRAM NM 60669-1 / IEC 60669-1 (4.5.1) | Rated current, voltage, poles, terminal cross-section |
  | Fixed socket outlet | IRAM-NM 60884-1 or IEC 60884-1 (4.5.6); the IRAM 2071 format is required by the AEA, not by the Anexo (ELEC-IRA-8) | 10 A or 20 A, 250 V, with earth |
  | Enclosure | IEC 60670-24 (box for protective devices, 4.2.11), IRAM 62670 (enclosures, 4.2.12) or IEC 62208 (empty enclosure, 4.2.13) | Modules, IP, IK, Class II or not, power dissipation |
  | Conduit | IRAM 62386-21 to -24 (insulating, 4.1.1 to 4.1.4); IRAM 2005 / IRAM-IAS U 500 2005 (semi-heavy steel, 4.1.9); IRAM 2205, IRAM-IAS U 500 2224, IRAM 2224 (light steel, 4.1.10 to 4.1.12); IRAM 2477 (meter pillar conduit, 4.1.13) | Printed classification, non-flame-propagating, compression resistance |
  | Cable tray | IEC 61537 (4.2.14) | Safe working load, electrical continuity, material |
  | Earth rod | IRAM 2309 (copper-bonded steel), IRAM 2310 (galvanized steel), IRAM 2314 (electrochemical) (4.6.2 to 4.6.4) | Diameter, length, engraving |

  Source of the table: Res. SIyC 236/2024, Anexo II in the text of Res. SIyC 26/2025 (IF-2025-17295098-APN-DNRT#MEC),
  items cited, per [iram-standards.md](iram-standards.md) (ELEC-IRA-2 and tables by family); Prysmian data sheets Ed. 2026,
  Schneider data sheet A9F74216 (2026), Kalop catalog; rules in [conductors-and-conduits.md](conductors-and-conduits.md),
  [protection.md](protection.md) and [panels.md](panels.md). The "shifted rows" note on SPDs and isolators
  referred to the original 2024 Anexo II: in the current one, the SPD is 4.5.14 (IRAM 2345 / IEC 61643-11) and the
  isolator is 4.5.15 (IEC 60947-3).
- **Verify:** you have the data sheet of the exact model (code), not a brochure for the family.
- **Don't:** decide by "the one everybody uses"; accept a seller's figure that is not in the data sheet.
- **Source:** those cited in the table.
### ELEC-FAB-5: State the origin only when you have verified it
- **Rule:** when recommending or describing a material, distinguish **Argentine brand**, **local manufacturing** and **imported**.
  Say "made in Argentina" only if the product, its data sheet or its certificate says so.
- **Why:** local manufacturing matters for getting spare parts, for technical support and for traceability, but
  "Argentine company" does not guarantee that the model is made here, and "imported" does not mean lower quality.
- **How:** where to look:
  - **Cables:** the printing on the sheath or insulation. Prysmian prints "Industria Argentina" on Superastic Jet / Flex,
    Afumex 1000+, Retenax Valio and Sintenax Valio (data sheets Ed. 2026). Also, IRAM license DC-E-P14-011.2 names the
    **production plant subject to inspection: Av. Argentina 6784, CABA**.
  - **Devices and accessories:** the package label ("Industria Argentina", "Hecho en ..." (made in ...), "Origen: ..." (origin: ...)) and the
    certificate (address of the production plant subject to inspection).
  - **Catalogs:** Kalop's says on the back cover "Fabricado y comercializado en Argentina por Acrópolis Cables S.A." (made and sold in Argentina by Acrópolis Cables S.A.)
    (Quilmes), but the company also says it "representa" (represents) products: confirm each item on its label. Jeluz's says
    that its products are made in its plant of more than 10,000 m², without detailing product by product.
- **Verify:** the origin you report matches the label of the product you are going to buy.
- **Don't:** say "es nacional" (it's Argentine-made) about a whole brand; say "it's Chinese, it's bad" or "it's European, it's good": the
  certificate and the data decide.
- **Source:** Prysmian data sheets Ed. 2026 ("Marcación" (marking) field); IRAM license DC-E-P14-011.2 (plant address); Kalop
  catalog (back cover); kalop.com.ar/empresa ("Diseñamos, fabricamos, representamos y comercializamos": we design, manufacture, represent and sell); Jeluz, Línea
  Protecciones catalog, p. 2.

## Cables

### Manufacturers and brands of low-voltage cables

| Manufacturer / brand | Company | Local manufacturing | Lines for fixed installations (declared standard) | Catalog |
|---|---|---|---|---|
| **Cimet** (Cimet Optel) | Argentine, more than 75 years old according to its site | Not verified (the site does not indicate a plant) | CC/V residential PVC (IRAM NM 247-3, 450/750 V, Cu class 5); Zerotox 750 residential LS0H (IRAM 62267, 450/750 V, Cu class 5); Ecoport CMXCC copper XLPE pre-assembled (aerial bundled) cable for service connections (IRAM 2164, 1 kV); Zerotox power XLPE/LS0H (IRAM 62266); Termolite power XLPE/PVC (IEC 60502-1); aluminum Ecoport (IRAM 2263); Laxica service connection (IRAM 63002) | cimet.com/productos |
| **Kalop** (Acrópolis Cables S.A.) | Argentine, Quilmes | Declared in the catalog ("Fabricado y comercializado en Argentina") | Kaloflex C5 (single-core PVC, class 5); Kaloflex LS0H C5; Kaloflex Energía and Energía LS0H (sheathed power cable, insulation and standard not confirmed); Kalobasic C4 (single-core PVC, medium flexibility); flexible cords (*tipo taller*) and parallel cords; Kalodur Cu (bare hard-drawn copper, IRAM 2004) | kalop.com.ar/catalogo/kalop-catalogo.pdf |
| **Marlew** | Argentine, offices in CABA | Probable (the site links a video "Planta Industrial Ezeiza" (Ezeiza industrial plant)); not verified | Residential / general installations, LV/MV power and control, Ecosafe (LSZH), fire-resistant, instrumentation, photovoltaic. Standards not published on the pages consulted | marlew.com.ar (catalog section) |
| **Prysmian** | International group; subsidiary Prysmian Energía Cables y Sistemas de Argentina S.A. (CABA) | Verified: "Industria Argentina" in the marking on the Ed. 2026 data sheets and plant at Av. Argentina 6784 (CABA) in the IRAM license | Superastic Jet and Superastic Flex: IRAM NM 247-3, 450/750 V, class 5 (the Ed. 2026 data sheet offers Jet up to 6 mm² and Flex "para secciones superiores" (for larger cross-sections); the certificate covers Jet from 0.5 to 6 mm² and Flex from 0.5 to 240 mm²). Afumex Green 750: IRAM 62267, LS0H. Afumex 1000+: IRAM 62266, 0.6/1 kV, LS0H. Sintenax Valio: IRAM 2178-1, PVC, 0.6/1 kV. Retenax Valio: IRAM 2178-1, XLPE, 0.6/1 kV. Retenax Preensamblado: IRAM 2263, aluminum. Also VN 202, PVN and TPR Ecoplus (cords), Prysun (solar) | ar.prysmian.com/es/catalogos |

Source: Prysmian data sheets Ed. 2026; IRAM license DC-E-P14-011.2; Kalop catalog; Cimet technical sheets 09 A2301 (CC/V), 10 A2301
(Zerotox 750) and 07 A2212 (Ecoport CMXCC), and product pages on cimet.com and marlew.com.ar (consulted 2026-11-15). The
standards for Cimet Zerotox power, Termolite, aluminum Ecoport and Laxica come from the names of their data sheets on the website, not from
opened data sheets: medium confidence.

**Brands we were asked to review and could not verify:** IMSA (site with an invalid TLS certificate), Argenplas (the domain
argenplas.com.ar is a plastics trade fair, not a cable manufacturer), Trefilcon, Epuyén, Fonseca. We are not saying they don't
exist or that they are bad: we found no documents to describe them. If they show up on site, apply ELEC-FAB-1, -2, -6,
-7 and -21.

### Published technical data: Prysmian Superastic Jet / Flex (IRAM NM 247-3, 450/750 V, class 5)

| Cross-section (mm²) | Max. wire diameter (mm) | Nominal insulation (mm) | Approx. outer diameter (mm) | Approx. mass (kg/km) | Max. resistance at 20 °C (Ω/km) |
|---|---|---|---|---|---|
| 1.5 | 0.26 | 0.7 | 3.0 | 20 | 13.3 |
| 2.5 | 0.26 | 0.8 | 3.6 | 31 | 7.98 |
| 4 | 0.31 | 0.8 | 4.1 | 45 | 4.95 |
| 6 | 0.31 | 0.8 | 4.7 | 63 | 3.30 |
| 10 | 0.41 | 1.0 | 6.0 | 107 | 1.91 |
| 16 | 0.41 | 1.0 | 7.0 | 167 | 1.21 |
| 25 | 0.41 | 1.2 | 9.6 | 268 | 0.78 |
| 35 | 0.41 | 1.2 | 10.8 | 361 | 0.554 |

Source: Prysmian, data sheet "Superastic Jet / Flex", Ed. 2026, p. 3 (catalog summary, not the standard). The resistances are the
maximums of IEC 60228 / IRAM NM 280 for class 5 bare copper; the Kalop catalog publishes the same values (19.5 / 13.3 /
7.98 / 4.95 Ω/km for 1 / 1.5 / 2.5 / 4 mm²). The mass is that of the complete cable (copper + PVC) and is specific to that product. The
current-carrying capacities are summarized in [current-ratings-and-devices.md](current-ratings-and-devices.md) and the underlying
rule is ELEC-CON-8.

### Prysmian lines by use (summary of Ed. 2026 data sheets)

| Line | Standard | Voltage | Insulation / sheath | Operating / short-circuit temp. | Conductor | Where it goes |
|---|---|---|---|---|---|---|
| Superastic Jet / Flex | IRAM NM 247-3 | 450/750 V | PVC, no sheath | 70 °C / 160 °C | Cu class 5 | Inside concealed or surface conduit, panel wiring |
| Afumex Green 750 | IRAM 62267 | 450/750 V | LS0H thermoplastic, no sheath | 70 °C / 160 °C | Cu class 5 | Same as above, in high-occupancy premises or where evacuation is difficult |
| Sintenax Valio | IRAM 2178-1 | 0.6/1 kV | PVC, sheathed | 70 °C / 160 °C | Cu class 5 up to 240 mm² (single-core) | Cable tray, direct burial or in duct, conduit |
| Retenax Valio | IRAM 2178-1 | 0.6/1 kV | XLPE, sheathed | 90 °C / 250 °C | Cu class 5 up to 6 mm², compacted class 2 above (single-core) | Cable tray, buried, power distribution |
| Afumex 1000+ | IRAM 62266 | 0.6/1 (1.2) kV | LS0H, sheathed | 90 °C / 250 °C | Cu class 5 up to 240 mm² (single-core) | Cable tray, free air, buried, where LS0H is required |
| Retenax Preensamblado | IRAM 2263 | 0.6/1.1 kV | XLPE, pre-assembled bundle | — | Class 2 aluminum phases, aluminum alloy messenger neutral | Service drop and overhead network (set by the utility) |

Source: Prysmian, Ed. 2026 data sheets for each line (ar.prysmian.com/es/catalogos).

### ELEC-FAB-6: Read the cable's printing before buying it and before pulling it
- **Rule:** a cable for fixed installation must have printed on it, repeated along its length, at least: **manufacturer or
  brand, line or designation, rated voltage, cross-section (and number of conductors if multi-core) and standard**, and the product
  must have its conformity marking (on the cable or on the coil). If any of those data is missing, it is not used. The
  **length marking** (meter by meter) is desirable, not mandatory: if the cable has it, use it to check the real length
  (ELEC-FAB-21).
- **Why:** the printing is the cable's identity once it is off the coil. It is what the inspector looks at, what lets you
  claim against the manufacturer and what gives away a 300/500 V cable sold as installation cable.
- **How:** real marking examples according to the data sheets:
  - Superastic: `PRYSMIAN - SUPERASTIC JET - Industria Argentina - 450/750V - Sección (mm²) - 247 NM 02-C5 BWF-B - Sello IRAM`.
  - Sintenax Valio: `PRYSMIAN - SINTENAX (logo Valio) - Antillama - Industria Argentina - 0,6/1 (1,2)kV. Cat. II Nro. de conductores x Sección (mm2) - IRAM 2178-1 - F24 - Marcación Secuencial de Longitud C/1 metro`.
  - Retenax Valio: `PRYSMIAN - RETENAX (logo Valio) - Industria Argentina - 0,6/1 kV. Cat. II - Nro. de conductores x Sección (mm2) - IRAM 2178-1 -F1 - Marcación Secuencial de Longitud C/1 metro`.
  - Afumex 1000+: `PRYSMIAN - AFUMEX 1000 + Industria Argentina - 0,6/1kV. - Cu o Al / 90 °C / IRAM 62266 / Nro. de conductores x Sección (mm2) / Marcación secuencial de longitud`.
  - Afumex Green 750 declares "Marcado metro a metro" (meter-by-meter marking).

  How to read it: "247 NM 02" is the IRAM NM 247-3 designation for 450/750 V fixed-installation cable; "C5" is
  class 5 (flexible) conductor; "450/750V" is the voltage. A **300/500 V** cable (whether an IRAM NM 247-5 cord or a
  single-core cable for internal wiring of appliances) is **not** suitable for fixed installation in conduit: 450/750 V is required there
  (247 NM 02 or IRAM 62267) (ELEC-CON-3).
- **Verify:** cut a sample length, read the full printing and compare it with the data sheet and the certificate (ELEC-FAB-2).
- **Don't:** accept cable with blurred or partial printing, or printing only on the coil label; accept "2.5" printed without
  standard or brand.
- **Source:** Prysmian data sheets Ed. 2026 (Superastic, Sintenax Valio, Retenax Valio, Afumex 1000+, Afumex Green 750),
  "Marcación" field; Res. SIyC 236/2024, Anexo II (text of Res. SIyC 26/2025), item 4.3.4 (IRAM-NM 247-3, unsheathed single-core cables for fixed
  installations, IEC 60227-3 MOD). **Not verified in a primary source:** the list of marking data required by IRAM NM 247-3 and the
  list of 300/500 V types it includes (paid standard; the rule takes the data that all the manufacturers reviewed print).

### ELEC-FAB-7: If you suspect the cable has less copper, measure the coil's resistance
- **Rule:** when in doubt about a cable (abnormal price, unknown brand, doubtful printing, cable that runs hot), measure the
  resistance of a **length you measured yourself** and compare it with the standard's maximum for its cross-section and class. If it is higher, beyond
  the instrument's uncertainty, the cable does not comply, even if it has the correct cross-section printed on it.
- **Why:** the "electrical" cross-section of a conductor is defined by its maximum resistance per kilometer (IEC 60228 / IRAM NM 280),
  not by its outer diameter. The typical counterfeit cable has less copper or impure copper and thicker insulation to disguise it:
  from outside it looks the same, but it has more resistance, runs hotter and leaves the protection poorly coordinated (ELEC-PRO-4).
- **How:**
  1. **Confirm the real length** (ELEC-FAB-21): measure it with a tape, use the meter-by-meter marking if the cable has it, or cut
     and measure a piece of known length. Don't use the length on the label: the short coil is another fraud and it also **hides** the
     missing copper in this test (see the second example).
  2. Leave the coil several hours at room temperature and in the shade before measuring, and measure the cable's temperature.
  3. Measure with a **milliohmmeter** (preferably 4-wire, Kelvin) or with the low-resistance / continuity function at 200 mA of
     an installation tester (IEC 61557-4), with the leads compensated ("null" or "zero" function). A common multimeter
     is not enough: the leads alone add tenths of an ohm. In a multi-core cable you can join the conductors in series at one end
     to measure twice the length.
  4. Correct to 20 °C: R20 = Rmeasured / [1 + 0.00393 × (t − 20)], with t the cable temperature in °C.
  5. Compare with the maximum: R20 ≤ Rmax (Ω/km) × length (km). If the result is **within ±5 % of the maximum**, the measurement
     is not enough to decide: repeat it with a 4-wire milliohmmeter or over a longer length. A good cable usually measures a few points
     below the maximum.

  | Cross-section (mm², class 5, bare Cu) | Rmax at 20 °C (Ω/km) | Rmax of a 100 m coil at 20 °C (Ω) | If the real copper were 20 % less, it would measure approx. (Ω) |
  |---|---|---|---|
  | 1.5 | 13.3 | 1.33 | 1.66 |
  | 2.5 | 7.98 | 0.80 | 1.00 |
  | 4 | 4.95 | 0.50 | 0.62 |
  | 6 | 3.30 | 0.33 | 0.41 |

  Source: Rmax from the Prysmian Superastic data sheet Ed. 2026, p. 3, and from the Kalop catalog (IEC 60228 class 5 values). The two
  right-hand columns are a **calculation** by this guide (Rmax × 0.1 km; and Rmax × 0.1 / 0.8).

  *Worked example 1 (full coil):* a "2.5 mm²" coil that you measured with a tape at 100 m reads 0.92 Ω with the cable at
  28 °C. R20 = 0.92 / (1 + 0.00393 × 8) = 0.92 / 1.031 = 0.89 Ω. The maximum is 7.98 × 0.1 = 0.798 Ω: it is 12 % higher, well
  above the ±5 % uncertainty. **It does not comply.** Return the lot and notify the distributor (ELEC-FAB-30).

  *Worked example 2 (the short-coil trap):* a "2.5" that actually has 2.1 mm² of copper has about
  7.98 × 2.5 / 2.1 = 9.5 Ω/km. If the coil says 100 m but contains 84 m, it reads 9.5 × 0.084 = 0.80 Ω, and against the
  100 m maximum (0.798 Ω) it seems to "comply". With the real length, the maximum is 7.98 × 0.084 = 0.67 Ω: it is 19 % higher and **does not comply**.

  *Uncertainty:* a 200 mA function with an accuracy of ±(2 % + 2 digits) and a resolution of 0.01 Ω has, at 0.80 Ω, an
  error of ±(0.016 + 0.02) = ±0.036 Ω, that is ±4.5 % (calculation with a typical accuracy; use the one in your instrument's manual).
- **Other tests (indicative, they don't replace the measurement):**
  - **Weight:** copper weighs 8.89 kg per km and per mm² (calculation with a density of 8.89 g/cm³): 2.5 mm² is about 22 kg of copper per
    km. The complete Superastic 2.5 mm² cable weighs about 31 kg/km according to the data sheet (about 3.1 kg per 100 m coil). A coil
    that weighs clearly less than its own manufacturer's data sheet says is suspicious, but weight does not distinguish between
    a short coil and missing copper, and it only detects gross fraud: the insulation has weight and varies between brands.
  - **Wires:** count the wires in a cut end and measure one with a micrometer: in class 5 the maximum wire diameter for
    1.5 and 2.5 mm² is 0.26 mm (Prysmian data sheet). Fewer and thinner wires than in a reference cable of the
    same cross-section are a warning sign.
  - **Copper color:**
    - Silver shine **in the core** of the wire when you cut or scrape it, with copper only on the outside (copper-clad aluminum, CCA):
      **reject immediately**. CCA is not copper and does not comply with the installation cable standard.
    - **Tinned** copper (silver on the outside, copper inside): it is legal if the data sheet declares it; compare it with the Rmax for
      tinned conductor, which is somewhat higher (IEC 60228 class 5 tinned: 1.5 mm² = 13.7 Ω/km; 2.5 mm² = 8.21 Ω/km).
    - **Darkened** copper: clean or scrape it; if it is sound inside, that alone is not a reason to reject and the resistance
      measurement decides.
- **Verify:** record the measurement (instrument, temperature, measured length, value) in the job file.
- **Don't:** "measure" the cross-section with calipers over the insulation; calculate against the label length; trust that
  if it has a mark it cannot fail (if the measurement does not pass, claim anyway, to the manufacturer and to the certification body).
- **Source:** maximum resistances of bare copper: Prysmian Superastic Jet / Flex data sheet Ed. 2026 p. 3 and Kalop catalog;
  temperature coefficient of copper 0.00393 /°C (reference value for annealed copper, IEC 60228). **Not verified in a
  primary source:** the resistances of tinned conductor (13.7 and 8.21 Ω/km, values from the IEC 60228 table supplied during
  the review, not read in a data sheet) and the accuracy of each instrument (check its manual); official Argentine alerts
  about specific lots of cables with less copper (a search on 2026-11-15 found none on argentina.gob.ar).
### ELEC-FAB-21: Verify the real length of the coil: the short coil is a separate fraud
- **Rule:** when you receive cable in coils, check the real length of at least one coil per lot (and of all of them if the brand
  is unknown or the price is abnormal). If it has less than what was invoiced, file a claim for the lot.
- **Why:** a coil that says 100 m and contains 80 or 90 m charges you for copper that is not there, leaves you short on the job and, as shown in
  ELEC-FAB-7, skews the resistance test in favor of the bad cable.
- **How:**
  - If the cable has **meter-by-meter marking**, read the mark at the outer end and the one at the inner end: the difference is the length.
  - If it does not, unroll it on a clean surface and measure it with a tape or a measuring wheel, or count it as you pass it
    through a cable length counter.
  - As a quick check, compare the coil's weight with the mass per km in **that** manufacturer's data sheet (for example,
    Superastic 2.5 mm²: 31 kg/km): a light coil is suspected of being a short coil **or** of missing copper; both are
    resolved by measuring the length and then the resistance.
- **Verify:** measured length written on the delivery note (*remito*) or in the job file, with a photo of the start and end marks if there are any.
- **Don't:** accept "los rollos vienen así de fábrica" ("the coils come like that from the factory"); use the label length for the resistance test.
- **Source:** Prysmian Superastic data sheet Ed. 2026 (mass per km) and data sheets with "Marcación Secuencial de Longitud" (sequential length marking) (Sintenax
  Valio, Retenax Valio, Afumex 1000+). **Not verified in a primary source:** a standard length tolerance for commercial
  coils, and official statistics or alerts about short coils (it is a known fraud on site, with no official document
  found in this edition).

### ELEC-FAB-8: Choose the line by where the cable goes, not by brand
- **Rule:** first define the location (conduit, cable tray, buried, premises with difficult evacuation, service connection) with
  [conductors-and-conduits.md](conductors-and-conduits.md) (ELEC-CON-2 and ELEC-CON-4); then look in each
  manufacturer's range for the line that complies with that standard.
- **Why:** each manufacturer has different trade names for the same type of cable. The name says nothing; the
  standard does.
- **How:**

  | Need | Standard you look for | Example lines (per manufacturer data sheets or website) |
  |---|---|---|
  | Single-core in conduit, dwelling | IRAM NM 247-3, 450/750 V | Prysmian Superastic Jet / Flex; Cimet CC/V; Kalop Kaloflex C5 (standard not read in the data sheet) |
  | Single-core in conduit, LS0H | IRAM 62267 | Prysmian Afumex Green 750; Cimet Zerotox 750; Kalop Kaloflex LS0H C5 (standard not read in the data sheet) |
  | Sheathed, cable tray or buried, PVC (70 °C) | IRAM 2178-1 | Prysmian Sintenax Valio |
  | Sheathed, cable tray or buried, XLPE (90 °C) | IRAM 2178-1 | Prysmian Retenax Valio |
  | Sheathed, LS0H | IRAM 62266 | Prysmian Afumex 1000+; Cimet Zerotox potencia |
  | Overhead service drop | IRAM 2263 (aluminum pre-assembled) / IRAM 2164 (copper pre-assembled) / IRAM 63002 (concentric); set by the utility | Prysmian Retenax Preensamblado (IRAM 2263); Cimet Ecoport CMXCC (IRAM 2164); Cimet Laxica (IRAM 63002, according to the name of its data sheet) |

  Source: Prysmian data sheets Ed. 2026; Cimet technical sheets 09 A2301, 10 A2301 and 07 A2212; product pages on cimet.com;
  Kalop catalog (lines, with no legible standard in the extracted text). **Kalop Kaloflex Energía and Energía LS0H:** sheathed
  power cable; its insulation (PVC or XLPE) and its standard were not confirmed in this edition: check the data sheet before assigning it the
  70 °C or 90 °C current-carrying capacity.
- **Verify:** the cable's printing states the standard in the middle column.
- **Don't:** use an unsheathed single-core cable "because it's a good brand" in a cable tray or buried; choose LS0H only by the trade name
  "libre de halógenos" (halogen-free) without the IRAM 62267 or 62266 standard printed; use the XLPE current-carrying capacity for a cable
  whose insulation you have not confirmed.
- **Source:** data sheets and pages cited; rules ELEC-CON-2 and ELEC-CON-4. **Not verified in a primary source:** current title and
  edition of IRAM 2164, IRAM 2263 and IRAM 63002 in the IRAM catalog (taken from the manufacturer data sheets).

## Protective devices (MCBs, RCDs, SPDs, fuses, contactors, motor protection circuit breakers)

**Brands with no data in these tables are not listed because we could not read their data sheets, not because they are worse.** The
tables with Schneider and Jeluz data are examples of how to read a data sheet.

### Manufacturers and lines of modular protective devices

| Brand | Company | Local manufacturing | Verified lines and published data | Catalog |
|---|---|---|---|---|
| **ABB** | International group | Origin not verified | S200 (MCBs (*térmicas*); tightening torque 2.8 N·m according to copies of the data sheet from distributors, medium confidence, see ELEC-TAB-14). Other data not verified in this edition | new.abb.com (could not be read) |
| **Chint** | International group | Origin not verified | Present on the market; data not verified in this edition | — |
| **Jeluz** | Argentine (Spegazzini and Banfield, Bs. As.) | Local manufacturing declared in general ("manufacturados en su expansiva planta de más de 10000 m²": manufactured in its expansive plant of more than 10,000 m²); **origin of the protective devices not verified** product by product | IEC 60898-1 MCBs, B, C and D curves, 6 to 63 A, in lines with Icn 3 kA (C curve), Icn = Ics 4.5 kA and Icn = Ics 6 kA; 80, 100 and 125 A D curve MCBs, Icn 6 kA, **per IEC 60947-2**; JZ / JZX RCDs (*diferenciales*) 2P and 4P of 16, 25, 40 and 63 A, IΔn 30, 100 and 300 mA types AC and A (10 mA only type AC, In ≤ 32 A), Inc 6 kA (JZ) and 10 kA (JZX); JZ-TGC1 contactors (6 to 95 A), mini contactors, thermal overload relays, JZ-TGD1 motor protection circuit breakers (*guardamotores*) | Línea Protecciones catalog (Catalogo_protecciones_General.pdf, cdn.shopify.com) |
| **Roker** | Argentine (Lomas del Mirador, since 1983) | Not verified for protective devices | Mentions MCBs and RCDs. Data not verified | roker.com.ar |
| **Schneider Electric** | International group; plant in Florida (Bs. As.) since 1982, according to its 2019 catalog | Verified in 2019 for switches and socket outlets (Base, Roda, Roda Class), MV switchgear cells and assembly of Easypact / Compact / Masterpact. **Not verified** for the Acti9 / Easy9 modular protective devices | See next table | se.com/ar/es |
| **Siemens** | International group | Origin not verified | Not verified in this edition | — |
| **Steck** | Brazilian group (site steck.com.br) | Origin not verified | steck.com.ar redirects to a page in Portuguese; no data sheets were read | steck.com.br |
| **WEG** | Brazilian group | Origin not verified | Present on the market with motor protection circuit breakers, contactors and miniature circuit breakers; data not verified in this edition | — |
| **Zoloda** (Zoloda S.A.) | Argentine, Burzaco (Bs. As.), since 1959; 12,000 m² plant | Declared on its site for its own line (terminal blocks, ferrules, accessories: see ELEC-FAB-27); **origin of the protective devices not verified** | Offers MCBs, RCDs (30 and 300 mA), SPDs (*DPS*) and fuse bases; standards and data sheets not read | zoloda.com.ar |

Source: Jeluz, Línea Protecciones catalog, pp. 2 (company), 5, 8, 11 and 14 (MCBs) and 18 (RCDs), downloaded
2026-11-15; roker.com.ar; Schneider Electric "Catálogo General Retail 2019", p. 2 (industrial plant); zoloda.com.ar
(consulted 2026-11-15). **Not verified in a primary source:** Sica (the site of the electrical materials brand returned an
error; the domain sica.net.ar belongs to SICA Metalúrgica Argentina, a **different** pressure vessel company, don't
confuse them), Genrod (site with an invalid TLS certificate), Kalop in protective devices (its current catalog does not include them), "Baw" (the
site baw.com.ar belongs to a welding group, not a protective device maker) and "Tacsa" (Tecnología Argentina en Cintas S.A., Hurlingham:
it makes insulating and heat-shrink tapes, not protective devices).

### Published data: Schneider Electric (Argentina)

| Line | Standard | In (A) | Curves | Breaking capacity | Notes | Source |
|---|---|---|---|---|---|---|
| Easy9 MCB | IEC 60898-1 | 6 to 63 | C | Icn 4500 A at 230 and 400 V | 1P to 4P; IRAM certificate DC-E-S26-042.4 (data sheet of the 2P C16) | Data sheet EZ9F34216 (2026-11-15); 2019 catalog |
| Easy9 RCD | IEC 61008-1 | 25, 40, 63 | — | — | **Type AC**, 30 mA, 2P and 4P; IRAM certificate DC-E-S26-002.20 (data sheet of the 2P 40 A) | Data sheet EZ9R36240 (2026-11-15); 2019 catalog |
| Easy9 SPD | IEC 61643-11 | — | — | Imax 20 kA, Up 1.5 kV | Class II (8/20 µs wave) | 2019 catalog, confirm it is current |
| iK60 | IEC 60898-1 | 6 to 63 | C | Icn 6000 A | 1P to 4P | 2019 catalog, confirm it is current |
| Acti9 iC60N | IEC 60898-1 and IEC 60947-2 | 0.5 to 63 (in AR: 10 to 63 on the product page) | B, C, D | Icn 6000 A (60898-1, 400 V); Icu 20 kA at 220-240 V and 10 kA at 380-415 V (60947-2) **in the data sheet of the 2P A9F74216**; for other pole configurations, see the data sheet for the code | Energy limiting class 3; tightening torque 2 N·m (16 A); IRAM certificate DC-E-S26-042.6 | Data sheet A9F74216 (2026-11-15) |
| Acti9 iC60H | IEC 60898 and IEC 60947-2 | 1 to 63 | B, C, D | Icn 10,000 A (60898). Icu (60947-2), from 6 to 63 A: 2P/3P/4P (F/F, phase-phase) 30 kA at 220-240 V and 15 kA at 380-415 V; 1P (F/N, phase-neutral) 15 kA at 220-240 V | — | 2019 catalog, p. 6, confirm it is current |
| C120N | IEC 60898 and IEC 60947-2 | 80 to 125 | B, C, D | Icu per IEC 60947-2, different by voltage (the text extracted from the 2019 catalog does not allow each value to be assigned to its voltage with certainty: confirm in the data sheet) | For incoming switches above 63 A (ELEC-FAB-25) | 2019 catalog, confirm it is current |
| iID RCD | IEC 61008 | 25 to 100 (2P), 25 to 125 (4P) | — | — | Type AC, and A-SI versions ("clase Asi" in the catalog: super-immunized type A, **not type B**, see ELEC-PRO-9); 10, 30, 100, 300 mA and 300 mA S | 2019 catalog, pp. 10 and 11, confirm it is current |

Source: the "Source" column of each row: Schneider Electric Argentina, "Catálogo General Retail 2019", pp. 3 to 11, and data
sheets generated on 2026-11-15 (A9F74216, EZ9F34216, EZ9R36240). The 2019 data may have changed: confirm in the current
data sheet for the exact code. The Domae line that appeared in other markets **was not verified** for Argentina in this edition.

### ELEC-FAB-9: Read the breaking capacity on the device and compare it with the Icc at that point, under the same standard
- **Rule:** choose each MCB with an **Icn per IEC 60898-1** greater than or equal to the prospective short-circuit current at
  the panel (ELEC-PRO-3). Read the value on the front of the device (the number in a rectangle, in A: 3000, 4500, 6000, 10000)
  and don't confuse it with the Icu of IEC 60947-2.
- **Why:** the same device has two different numbers depending on the standard. The Acti9 iC60N 2P, for example, has Icn = 6000 A
  (IEC 60898-1) and Icu = 20 kA at 230 V (IEC 60947-2). For dwellings, offices and shops the AEA requires IEC 60898-1: if
  you compare with the Icu, you overestimate the device's capacity. And the lines are not interchangeable: a 3 kA line (for
  example, Jeluz C curve 3 kA) does not replace a 4.5 or 6 kA one, and a 4.5 kA one (Easy9) does not replace a 10 kA one (iC60H)
  in a panel close to the transformer.
- **How:**
  1. Calculate the prospective Icc at the panel with `gateway electricidad coordinate` or ask the utility for it.
  2. Look in the data sheet for the line with sufficient Icn. If the Icc exceeds the Icn of the line you want to use, move up a line;
     backup protection ("filiación", cascading) is only valid with the manufacturer's table for that exact combination (ELEC-PRO-3).
  3. For incoming switches above 63 A the device falls outside the mandatory materials certification regime (point 2.e
     of the annex), but not outside the product standards: still demand the data sheet with standard and breaking capacity (ELEC-FAB-25). Watch out:
     some modular MCBs of 80 to 125 A are declared only per IEC 60947-2 (for example, Jeluz 80-125 A D curve).
- **Verify:** the number in the rectangle on each MCB ≥ Icc at the panel; if the device only shows Icu (60947-2), it is not
  suitable as the PIA of a panel operated by ordinary users (ELEC-NOR-14).
- **Don't:** buy "the 10 kA one" without checking whether that number is Icn or Icu; mix lines with different Icn in a panel without
  checking the point.
- **Source:** Schneider data sheet A9F74216 (2026-11-15); Catálogo Retail 2019 (iK60, iC60H); data sheet EZ9F34216 (Easy9); Jeluz,
  Línea Protecciones catalog, pp. 5, 8, 11 and 14; ELEC-PRO-3 for the AEA requirement; Disp. DNRT 2/2025, Anexo, point 2.e.

### ELEC-FAB-10: Busbar combs (*peines*), accessories and replacements: same brand and line, or a new verification
- **Rule:** the busbar comb (*peine*, connection bar), add-on RCD blocks, auxiliary contacts and covers must be from the
  **same manufacturer and line** as the devices they connect. If you replace a device in an assembled panel, use the same
  line; if you change brand, redo the coordination check (ELEC-PRO-10) and the selectivity check (ELEC-PRO-21).
- **Why:** the comb is designed for the terminal geometry, the pole pitch (18 mm in the modular lines reviewed) and
  the current of that line. A comb from another brand may fit "more or less", clamp on the insulation, overheat or leave
  poles not tightened. The ID/PIA coordination and selectivity tables each manufacturer gives are valid only for its own
  devices.
- **How:**
  - Example of published comb data: Schneider Acti9 A9XPH212 (two-pole, 12 modules of 18 mm): pole pitch 18 mm;
    rated operational current Ie 100 A at 40 °C; standard EN/IEC 61439-1 (Ui 500 V per IEC 61439-2); end caps and tooth
    covers mandatory when cut. Easy9 has its own 80 A comb. Each line has its own.
  - Before buying, check that spare parts for that line are in stock in your area: a panel of a brand with no local
    distribution becomes hard to maintain.
  - Write down the brand, line and code of each device on the single-line diagram (ELEC-TAB-18): whoever comes next will know what to replace.
- **Verify:** comb from the same manufacturer as the devices, with end caps, tightened to the torque in the data sheet (ELEC-TAB-14).
- **Don't:** mix combs from different brands; use a "universal" comb with no data sheet; jumper with leftover pieces of comb.
- **Source:** Schneider Electric, data sheet A9XPH212 (2026-11-15) and Catálogo Retail 2019, p. 9 (Acti9 combs) and p. 30 (Easy9
  80 A comb); ELEC-TAB-13 and ELEC-TAB-14; ELEC-PRO-10 and ELEC-PRO-21. **Not verified in a primary source:** declared
  compatibility or incompatibility between combs of different brands; the rule is a judgment call (without manufacturer data no
  verification is possible).

### ELEC-FAB-11: RCDs (*diferenciales*): read the type and sensitivity in the catalog, don't assume
- **Rule:** before buying an RCD, confirm in the data sheet: **type** (AC, A, F, B), **IΔn** (10, 30, 100, 300 mA),
  **S** if selective, **In** and **poles**. In line with ELEC-PRO-9:
  - **type A** as the recommended minimum for circuits with single-phase electronics (inverter AC or refrigerator, induction cooktop,
    washing machine, power supplies, UPS);
  - **type F** with single-phase variable frequency drives;
  - **type B** (or type A / F + RDC-DD per IEC 62955) for EV chargers without DC detection,
    three-phase drives and the photovoltaic inverters that require it.
- **Why:** budget lines are often type AC only (Easy9, for example, appears only as type AC in the 2019 catalog and
  in the 2026 data sheet). A type AC may not trip with leakage that has a DC component, and smooth DC above
  6 mA can "blind" an upstream AC or A.
- **How:** on the front of the device, the type symbol (sine wave alone = AC; sine + pulsating = A) or the letter, and the
  IΔn value. In the data sheet, the conditional short-circuit current and with which upstream protection it is guaranteed
  (ELEC-PRO-10). "Superinmunizado" (super-immunized: A-SI, "clase Asi") is a variant of type A, not a type B.
- **Verify:** type symbol and "S" (if applicable) printed on the device; the equipment manual does not ask for a higher type;
  test each one with an RCD tester at commissioning (ELEC-MED-6).
- **Don't:** buy "un disyuntor de 30 mA" ("a 30 mA RCD") without looking at the type; install an AC where the rule calls for A; install a type AC or A RCD (ID)
  upstream of an EV charger without DC detection.
- **Source:** Schneider Electric, data sheet EZ9R36240 (2026-11-15) and Catálogo Retail 2019, p. 3 (Easy9 type AC) and pp. 10-11 (iID and
  clase Asi); Jeluz, Línea Protecciones catalog, p. 18; ELEC-PRO-9 (which cites AEA 90364-7-722 Ed. 2024, 722.531.2.101) and
  ELEC-MED-6. The type A requirement for dwellings was not found in AEA 771/770 (see ELEC-PRO-9): here it is a recommendation.
### ELEC-FAB-12: How to spot a counterfeit MCB (*térmica*) or RCD (*diferencial*)
- **Rule:** at any of these signs, the device is not installed until it is verified: no conformity marking, or a QR code
  that does not open; incomplete printed data (no standard, no Icn, no curve); poor finish (burrs, crooked letters,
  colors different from the original); weight clearly lower than an original from the same line; price far below what
  the official distributor charges; sold loose, without packaging, or through a channel that is not in the manufacturer's network.
- **Why:** a counterfeit MCB may not trip on overload or may explode on a short circuit, and a counterfeit (*trucho*) RCD
  may lack the toroidal transformer that detects leakage: the test button "works" but it does not protect.
- **How:**
  1. Compare with an original bought from the official distributor: weight, typeface, code number, hologram or QR code on the packaging.
  2. Scan the QR code and verify the certificate (ELEC-FAB-1). If the brand publishes the certificate number on the product
     data sheet (as Schneider does: DC-E-S26-042.6 for the iC60N, DC-E-S26-042.4 for the Easy9 MCB), compare it.
  3. RCDs: test it with a tester that measures trip time and trip current, not only with the button (ELEC-MED-6). If it does
     not trip at IΔn within the time set by the standard, remove it.
  4. Ask the manufacturer: most have technical support that can validate a batch code.
- **Verify:** valid QR code + certificate for the model + test with an instrument.
- **Don't:** open the device "to see if it has a toroid" and install it afterwards; leave it in the panel "until I get
  another one".
- **Source:** criterion of this guide based on ELEC-FAB-1 and ELEC-MED-6; Schneider data sheets A9F74216 and EZ9F34216 (certificate
  numbers). **Not verified in a primary source:** official Argentine alerts about batches of counterfeit MCBs or RCDs
  of specific brands (a search on 2026-11-15 found none on argentina.gob.ar).

### ELEC-FAB-22: SPDs (*DPS*) and voltage protectors: choose them by the data sheet, not by the "kA" on the front
- **Rule:** buy an SPD with a data sheet that states the **standard (IRAM 2345 or IEC 61643-11), type (1, 2 or 3), Uc, Up, In (or Iimp for
  type 1), required backup protection and connection scheme**, and with conformity marking (it falls under the
  technical regulation and only accepts a certificate under scheme 1b or 5). Buy an over- and undervoltage protector (voltage relay or
  POP protector) with a data sheet that states the adjustment range, reconnection time, breaking current or the contactor it
  drives, and **the maximum voltage it withstands without damage** (it has to withstand the 380 V of a broken neutral). How to choose
  and mount them: ELEC-PRO-17, ELEC-PRO-18 and ELEC-PRO-19.
- **Why:** an SPD with a low Uc is destroyed by the normal overvoltages of the grid; one without backup protection can burn the
  panel when it reaches end of life. The SPD does not protect against a broken neutral: the voltage protector does that. A
  voltage protector that does not withstand 380 V burns out exactly in the event you installed it for.
- **How:**
  - Example of published data: Schneider Easy9 SPD, IEC 61643-11, class II (8/20 µs wave), Imax 20 kA, Up 1.5 kV (2019
    catalog). Uc and In are missing from that summary: ask for the data sheet of the code.
  - Don't compare SPDs of different types by Imax (the test waves are different, ELEC-PRO-17).
  - Plug-in protectors for a single appliance: they work for that appliance, they do not protect the installation (ELEC-PRO-19).
- **Verify:** data sheet with the data in the rule; conformity marking; end-of-life indicator visible in the panel.
- **Don't:** buy a "40 kA" SPD without Uc or Up on the data sheet; use an SPD as protection against a broken neutral;
  replace a spent SPD with one of a different Uc.
- **Source:** Res. SIyC 236/2024, Anexo II (text of Res. SIyC 26/2025), item 4.5.14 (SPD: IRAM 2345 or IEC 61643-11); Disp. DNRT 2/2025, Anexo, point 5.2.3 (schemes 1b or 5 for
  SPDs); IRAM catalog as per [iram-standards.md](iram-standards.md), ELEC-IRA-14 (IRAM 2345 / IEC 61643-11); Schneider Catálogo Retail
  2019 (Easy9 SPD); ELEC-PRO-17 to ELEC-PRO-19. **Not verified in a primary source:** data sheets of voltage protectors from
  brands on the Argentine market (none could be read for this edition) and data sheets of SPDs from other brands.

### ELEC-FAB-23: Fuses and fuse bases: same standard, same system and same size
- **Rule:** fuses and fuse bases with **IEC 60269** (the standard in the technical regulation), of the same system (NH,
  cylindrical, etc.) and size, with the utilization category (gG for cables, aM only as backup for motors) and the breaking capacity
  printed. Where fuses are allowed and how they are sized: ELEC-PRO-20.
- **Why:** a fuse of another size or another category fits "more or less" in the base, heats at the contact, or does not clear the
  short circuit it should. A fuse without data does not let you verify coordination.
- **How:** ask for the data sheet with In, category (gG / aM), size (NH 00, 1, 2, 3 or cylindrical 10×38, 14×51, 22×58), voltage and
  breaking capacity; and the base's data sheet with its maximum current and whether it isolates on load or off load. Fuse pullers and PPE
  for NH fuses (ELEC-SEG).
- **Verify:** fuse and base of the same system and size; category and rating match the single-line diagram.
- **Don't:** replace a fuse with a higher-rated one "because it kept blowing"; put in a wire; touch the NH fuses in the service box (*caja de toma*)
  of the utility (distribution company) (ELEC-PRO-20).
- **Source:** Res. SIyC 236/2024, Anexo II (text of Res. SIyC 26/2025), item 4.5.16 (LV fuses and fuse bases, IEC 60269); ELEC-PRO-20.
  **Not verified in a primary source:** manufacturers of fuses and bases present on the Argentine market (Zoloda lists fuse
  bases on its website, no data sheet read) and the cylindrical cartridge sizes of each line.

### ELEC-FAB-24: Contactors, motor protection circuit breakers (*guardamotores*) and thermal overload relays: data sheet with utilization category and coordination
- **Rule:** contactors with **IEC 60947-4-1**, operational current in the right category (AC-1 for resistive loads,
  AC-3 for motors), coil voltage and auxiliary contacts; motor protection circuit breakers with **IEC 60947-2 / IEC 60947-4-1**, an adjustment
  range that includes the motor's nameplate current, and their Icu / Ics at the panel voltage; and the manufacturer's **coordination table**
  (type 1 or type 2) for the exact combination. Where and why they are used: ELEC-PRO-24.
- **Why:** a contactor chosen by "amperes" without a category welds shut with a motor; a motor protection circuit breaker with an Icu lower than the
  panel's Icc does not clear the short circuit; type 2 coordination is only valid with the devices in the manufacturer's table.
- **How:** example of how to read a data sheet (Jeluz, catálogo Línea Protecciones): JZ-TGC1 contactors from 6 to 95 A, Ue up to
  690 V, "type 2" coordination, conditional short-circuit current Iq 50 kA; JZ-TGCA mini contactors from 6 to 12 A,
  "type 1" coordination, Iq 1 kA, which do **not** clear short circuits; JZ-TGD1-32 motor protection circuit breaker with Icu and Ics by voltage and by
  range (for example, range 24-32 A: Icu 50 kA at 230/240 V and 10 kA at 400/415 V). Look at the values for your range and your voltage.
- **Verify:** contactor, relay or motor protection circuit breaker and backup fuse or PIA appear together in the manufacturer's coordination
  table; motor protection circuit breaker set to the nameplate current.
- **Don't:** mix a contactor of one brand and a thermal overload relay of another without a coordination table; use a mini contactor as
  if it cleared short circuits.
- **Source:** Res. SIyC 236/2024, Anexo II (text of Res. SIyC 26/2025), item 4.5.5 (contactors: IEC 60947-1 + IEC 60947-4-1, or IEC 61095); Jeluz, catálogo Línea Protecciones
  (contactors, mini contactors, thermal overload relays and motor protection circuit breakers; the data sheet of the JZ-TGD1-80 motor protection circuit breaker cites a Chinese standard,
  GB/T 19334, for rail mounting, which is not enough to state the origin); ELEC-PRO-24. **Not verified in a primary
  source:** current data sheets of Schneider TeSys, Siemens Sirius, ABB or WEG (not read for this edition).

### ELEC-FAB-25: Circuit breakers above 63 A: outside mandatory certification, but not outside the standard
- **Rule:** for building incoming switches, common services panels or sub-panels above 63 A (modular circuit breakers
  from 80 to 125 A or molded case), require a data sheet with the **standard (IEC 60947-2; IEC 60898-1 if the panel is operated by
  uninstructed persons and the device declares it), In or setting range, Icu and Ics at the panel voltage, curve or
  trip settings, poles, and selectivity table** with the downstream devices, even though the device is not covered
  by mandatory certification.
- **Why:** Disp. 2/2025 excludes materials above 63 A (except cables) from the certification regime, so the
  conformity marking does not protect you there: the only guarantee is the manufacturer's data sheet and the purchase channel. Also,
  molded case circuit breakers have market withdrawals too: in 2023 Uruguay published a recall of
  ComPact NSX 400-630, EasyPact CVS/EZC/EZS 400-630 and PowerPact L 250-600 circuit breakers made in China in 2019 and 2021, because a
  component could come loose and the breaker fail to trip.
- **How:** ask for the data sheet of the exact code; verify Ics ≥ Icc at that point (ELEC-PRO-3) and selectivity (ELEC-PRO-21);
  record the device's date code or batch code in the file so you can cross-check it against a future recall; ask the
  manufacturer whether there are active campaigns for that model.
- **Verify:** data sheet with standard, Icu / Ics and settings; batch code recorded; settings adjusted according to the design.
- **Don't:** buy a used or salvaged (*de desarme*) incoming circuit breaker without a data sheet or known origin; set it to maximum "so it
  doesn't trip".
- **Source:** Disp. DNRT 2/2025, Anexo, point 2.e; Res. SIyC 236/2024, Anexo II (text of Res. SIyC 26/2025), item 4.5.11 (LV circuit breakers, IEC
  60947-2); Ministerio de Economía y Finanzas de Uruguay (Uruguayan Ministry of Economy and Finance), alert/recall of 2023-03-13 (gub.uy); Jeluz, catálogo Línea
  Protecciones, p. 14 (80-125 A according to IEC 60947-2); Schneider Catálogo Retail 2019 (C120N). **Not verified in a primary
  source:** an equivalent Argentine alert (not found on argentina.gob.ar on 2026-11-15) and whether those batches were sold
  in Argentina.

## Socket outlets, switches and plugs

### Manufacturers and lines

| Brand | Company | Local manufacturing | Lines | Published data |
|---|---|---|---|---|
| **Cambre** | Argentina; Centro Industrial Garín, Bs. As. | Industrial address verified; which products are made there, not verified | Siglo XXI, Siglo XXII, Bauhaus, A.R.T.E.; residential, hospital, hotel, marine and lighting control solutions | Standards not published on the pages consulted |
| **Jeluz** | Argentina; Spegazzini and Banfield, Bs. As. (offices, industrial plant and logistics center) | Industrial plant declared; products by plant, not verified | Línea Modular (Essenza, Cristal, Mito, Verona 2000, Platinum, Regina, B.O., N.B.O. cover plates), Módena and Florencia assembled units, Superficie y Estanco (surface and weatherproof), Fichas (plugs), Prolongadores (extension cords) | Standards not read in the downloaded catalog |
| **Kalop** | Argentina (Acrópolis Cables S.A., Quilmes) | Declared in the catalog | Modular system (Zen Metals and others), socket outlets and switches, Heavy Duty plugs, industrial plugs and sockets (IP44, IP67), extension cords | Socket outlet IRAM 2071 10 A / 250 V and 20 A / 250 V; safety shutter according to IEC 60884-1 |
| **Richi** | Argentina; Villa Madero (Bs. As.), since 1953 | Declared on its website ("desarrollamos y fabricamos", "we develop and manufacture"); product by product, not verified | Quantum Bio, Quantum Box, Quantum Era, Quantum Geo, Quantum Net, Serie Conexión | Standards not published on the page consulted |
| **Schneider Electric** | International group | Verified in 2019: Base, Roda and Roda Class switch rockers at the Florida plant | Base, Roda, Roda Class; Pratika industrial plugs and sockets | See current catalog |

Source: cambre.com.ar (address and lines), jeluz.net (lines and addresses), Kalop catalog (modular system and industrial plug
pages), richi.com.ar (consulted 2026-11-15), Schneider Catálogo Retail 2019 p. 2. **Not verified:** Sica (socket outlet and switch
lines, website with an error) and Plasnavi (no documents found).

### ELEC-FAB-13: Earthed socket outlets (*tomas*) IRAM 2071, rated for the circuit, and modules from the same line as the frame
- **Rule:**
  - Fixed-installation socket outlets: earthed, **IRAM 2071** format, **10 A** on general-purpose circuits and **20 A** only
    where the circuit and the load justify it (TUE or a dedicated circuit, ELEC-CIR-9), certified according to IRAM-NM 60884-1
    or IEC 60884-1.
  - "Universal" socket outlets that accept plugs of different geometries at the same time are prohibited.
  - Modules, frames and cover plates of the same brand and line.
- **Why:** the universal socket outlet does not guarantee the earth contact or the contact pressure, and it overheats. Modules of one
  brand do not fit safely in another brand's frame: they stay loose and the terminal moves.
- **How:** ask for the module's data sheet with standard, current and terminal cross-section. Plugs (*fichas*) of 10 A and of 20 A in the
  Argentine format do not fit the socket outlet of the other current, and that is on purpose. In bathrooms, kitchens and outdoors check the IP of the
  assembly (cover with membrane or weatherproof).
- **Verify:** on the back of the module, standard, 10 A or 20 A and 250 V; earth connected (ELEC-PAT-14).
- **Don't:** swap a 10 A socket outlet for a 20 A one on a TUG to plug in an air conditioner, an oven or a heater with a
  20 A plug: that load goes on a TUE or a dedicated circuit (ELEC-CIR-9); cut the 20 A plug off an appliance to fit a
  10 A one; mix modules of different brands in the same frame.
- **Source:** Disp. DNRT 2/2025, Anexo IF-2025-38164600-APN-DNRT#MEC, point 4.1.a (fixed earthed socket outlets, IRAM-NM 60884-1 or
  IEC 60884-1, no multiple geometries); Res. SIyC 236/2024, Anexo II (text of Res. SIyC 26/2025), item 4.5.6 (IRAM-NM 60884-1 / IEC 60884-1; the
  IRAM 2071 format does not appear in the Anexo, it is required by the AEA); IRAM catalog as per [iram-standards.md](iram-standards.md),
  ELEC-IRA-8 (IRAM 2071 ed. 3, 2009-11-12); Kalop catalog (socket outlet IRAM 2071 10 A and
  20 A); ELEC-PAT-14 and ELEC-CIR-9. **Not verified in a primary source:** the 10 A and 20 A geometry in the text of IRAM
  2071/2073 (paid standard; the incompatibility between the two is published reference information, not read in the standard) and the
  stated incompatibility between modules of different brands (site practice).

### ELEC-FAB-26: Light switches (*llaves de efecto*): standard, current and terminal, and from the same system as the frame
- **Rule:** buy light switches (fixed-installation manual switches) with **IRAM-NM 60669-1** (or IEC
  60669-1) printed, with their **rated current and voltage** marked, and the conformity marking
  (they are covered and only accept a certificate under scheme 1b or 5). The rated current of the switch must be greater than or
  equal to that of the load it switches, and the terminal must accept the cross-section of the circuit.
- **Why:** a switch that switches a heater or a motor above its rated current gets charred; a terminal that
  does not accept the cable forces you to "thin it" by cutting strands.
- **How:** look at the back of the module: standard, current (for example 10 A or 16 A), 250 V, maximum terminal cross-section. For large
  loads or motors, the switch controls a contactor (ELEC-FAB-24) instead of switching the load directly. If the design requires
  switching phase and neutral (for example, an outdoor appliance), use a **double-pole** switch with that marking on the body.
- **Verify:** rated current of the switch ≥ current of the load; standard printed; module from the same line as the
  frame.
- **Don't:** use a light switch to switch a water heater or an air conditioner; switch only the neutral with a single-pole switch.
- **Source:** Res. SIyC 236/2024, Anexo II (text of Res. SIyC 26/2025), item 4.5.1 (manual switches: IRAM NM 60669-1 / IEC 60669-1); Disp. DNRT
  2/2025, Anexo, point 5.2.3 (schemes 1b or 5 for manual switches); [iram-standards.md](iram-standards.md), ELEC-IRA-21.
  **Not verified in a primary source:** the rated currents each brand on the market offers (no switch module data sheets
  were read for this edition) and an AEA requirement for a double-pole switch in specific locations.
### ELEC-FAB-14: Plugs (*fichas*), power strips (*zapatillas*) and extension cords (*prolongadores*): earthed, 10 A and with a limiter
- **Rule:** plugs **with earth up to 20 A according to IRAM 2073** (or an IEC TR 60083 format) and **without earth up to 10 A according to
  IRAM 2063** (or IEC TR 60083), in both cases complying with IRAM-NM 60884-1 or IEC 60884-1. Power strips and extension cords with
  earthed socket outlets, a **10 A maximum simultaneous** legend and, if they have several outlets, an **automatic 10 A limiter**.
- **Why:** the extension cord is the most abused part of the installation and the one that causes the most house fires when it is
  overloaded. A 2000 W heater draws 2000 / 220 = 9.1 A: it is already at the edge of the 10 A limiter, without adding anything else.
- **How:** look at the legend on the body and the limiter (a reset button). Industrial plugs (IEC 60309) are another
  family, for construction sites and machines (see [site-safety.md](site-safety.md)).
- **Verify:** 10 A legend on the body, limiter on multi-outlet ones, conformity marking.
- **Don't:** plug heating appliances, air conditioners, electric kettles (*pava*), ovens or cooktops into power strips or extension cords,
  with or without a limiter: they go straight into the wall socket outlet of the right circuit (ELEC-CIR-9); daisy-chain power strips; swap
  a 20 A plug for a 10 A one.
- **Source:** Disp. DNRT 2/2025, Anexo IF-2025-38164600-APN-DNRT#MEC, points 4.1.b (portable socket outlets and extension cords)
  and 4.1.c (plugs: IRAM 2073 / IRAM 2063 or IEC TR 60083 formats, with IRAM-NM 60884-1 or IEC 60884-1); IRAM catalog as per
  ELEC-IRA-9 (IRAM 2073 ed. 3 and IRAM 2063 ed. 4, both 2009-11-12); ELEC-CIR-9.

## Conduits, boxes, enclosures and panel accessories

### Manufacturers and lines

| Brand | Company | Local manufacturing | Products | Published data |
|---|---|---|---|---|
| **Conextube** | Argentina, since 1979; plant in William C. Morris (Hurlingham) | Plant declared on its website | Luxury Black insulating consumer units (4 to 54 modules), GRP (*PRFV*) enclosures for underground networks, Acotube+ double-insulated down conduit (meter pillar kit) | Luxury Black: IRAM 62670, IP41 |
| **Jeluz** | Argentina | Not verified per product | Conduit systems (rigid and corrugated conduit, flush and junction boxes); Dinbox enclosures (4 to 36 modules, IP41), Dinbox PRO (4 to 54 modules, IP41, flush and surface mounted) and Dinbox IP (4 to 36 modules, IP66, surface mounted) | Conduits with their IRAM 62386 classification printed in the catalog, for example 4432 (1250 N, for slabs), 4321 (1250 N), 3321 (750 N) and 2321 (320 N) |
| **Kalop** | Argentina (Acrópolis Cables S.A.) | Declared in the catalog | Kaloductos (rigid PVC conduit and fittings), surface trunking, junction boxes (IP40, IP55), boxes for DIN protective devices | PVC conduit bending according to IRAM 62386-1 and IRAM 62386-21; DIN boxes according to IEC 60670, IP20, glow wire 650 °C |
| **Roker** | Argentina, since 1983; head office in Lomas del Mirador; metal enclosure plant opened in 2021 | Declared on its website (no plant address) | Boxes, surface trunking, conduits, plastic enclosures; C10, Utopía and Místico metal enclosures; metering lines | C10: IRAM and IEC standards, IP65, IK08 / IK10; "more than 500 certified products" |
| **Schneider Electric** | International group | Not verified | Easy9 boxes (flush and outdoor), Kaedra weatherproof boxes, Dexson surface trunking | Easy9: IEC 60670-1, 63 A (5 to 24 modules) and 80 A (36 and 48), Icc 10 kA, IP40 / IK07, 650 °C |
| **Zoloda** | Argentina, Burzaco, since 1959 | Declared on its website: own design, tooling and production, 12,000 m² plant | Assembled terminal blocks, terminals, insulated bootlace ferrules, cable lugs, flexible conduit, surface trunking, DIN accessories | Product standards not published on the page consulted (it declares ISO 9001:2015, which is a system standard, not a product standard) |

Source: conextube.com, jeluz.net (Canalizaciones catalog and distribution item list, downloaded 2026-11-15),
Kalop catalog, roker.com.ar, zoloda.com.ar, Schneider Catálogo Retail 2019 p. 30 (consulted 2026-11-15). **Not verified:**
Genrod (website with an invalid TLS certificate; a brand widely used for enclosures and boxes), Tubelectric (domain does not resolve), Daisa (the
domain redirects to another company), Tecnocom and Steck (not accessible). For light, semi-heavy and heavy steel conduit we could not
verify manufacturers in this edition: the standard in ELEC-FAB-15 applies.

### ELEC-FAB-15: Conduits (*caños*) and boxes: flame non-propagating and with their standard printed; no drain pipes or unmarked corrugated conduit
- **Rule:** every conduit and box of the electrical installation must be **flame non-propagating** (the insulating ones) and have
  its standard printed:
  - insulating conduits: **IRAM 62386 / IEC 61386** family (rigid -21, pliable or corrugated -22, flexible -23, buried
    -24), with the classification printed;
  - **semi-heavy** steel conduit: IRAM 2005 / IRAM-IAS U 500 2005; **light** steel: IRAM 2224 / IRAM-IAS U 500 2224 (threaded)
    or IRAM 2205 (plain);
  - boxes: **IRAM 2346** (insulating, flush), **IRAM 2353** (insulating, surface), **IRAM 62005** (semi-heavy
    metal), **IRAM 62224** (light metal) or **IEC 60670-21 to -24**.

  Drain pipe (the "caño naranja", "orange pipe", from the builders' merchant (*corralón*)), any water pipe and any unmarked corrugated conduit are not used.
- **Why:** a flame-propagating conduit carries fire from box to box inside the wall, and a conduit without a classification does not guarantee
  the compressive strength the location requires (in a concrete slab, for example).
- **How:**
  - Choose the type for the location with ELEC-CON-11 (steel, rigid PVC, corrugated) and the minimum classification according to
    [conductors-and-conduits.md](conductors-and-conduits.md).
  - On the conduit, look for the printing: brand, standard, diameter and classification (for example, in the Jeluz catalog: "classification
    4432 according to IRAM 62386", compressive strength 1250 N, for slabs). Color guarantees nothing: the printing rules.
  - Fittings (bends, couplings, connectors, boxes) from the same line as the conduit.
- **Verify:** printing on the conduit and on the box. As an indicative test, on a small offcut, outdoors, away from
  construction materials and without breathing the smoke (burning PVC gives off toxic and corrosive gases): when the flame is removed, a
  non-propagating material goes out by itself. The printing and the certificate rule, not this test.
- **Don't:** buy unbranded corrugated conduit "because it's the same"; use bends heated with a blowtorch on PVC; use water
  or drain pipes; do the flame test on site or on installed material.
- **Source:** Res. SIyC 236/2024, Anexo II in the text of Res. SIyC 26/2025 (IF-2025-17295098-APN-DNRT#MEC), items 4.1.1 to 4.1.13
  (conduits, including the meter pillar conduit IRAM 2477) and 4.2.1 to 4.2.14 (fittings, boxes, enclosures, cabinets and trays); Kalop catalog (IRAM 62386-1 and IRAM 62386-21 for bending PVC conduit; IEC 60670 for boxes); Jeluz
  Canalizaciones catalog (IRAM 62386 classifications); ELEC-CON-3, ELEC-CON-11 and ELEC-CON-14; ELEC-IRA-11. Heavy conduit
  (IRAM-IAS U 500 2100) does not appear in Anexo II: see [conductors-and-conduits.md](conductors-and-conduits.md).

### ELEC-FAB-16: Enclosures (*gabinetes*): choose by standard, modules, IP, Class II and dissipable power
- **Rule:** the panel enclosure must have a data sheet with the **standard** (IEC 60670-24 / IRAM 62670, or IEC 62208), **number
  of 18 mm modules**, **IP**, **IK**, whether it is **Class II**, and the **power it can dissipate**. Choose it with 20 % spare
  (ELEC-TAB-7).
- **Why:** the main panel must be Class II (ELEC-TAB-2) and must not overheat with all devices
  loaded. An enclosure without a data sheet does not let you verify either of the two.
- **How:** examples of published data: Conextube Luxury Black, IRAM 62670 and IP41; Jeluz Dinbox and Dinbox PRO, IP41, and Dinbox
  IP, IP66 (for damp locations or covered outdoor areas); Schneider Easy9, IEC 60670-1, IP40 / IK07, 63 or 80 A depending on size, Icc
  10 kA; Roker C10 metal, IP65 and IK08 / IK10. **A metal enclosure (like the C10) is not Class II:** it is for sub-panels (*tableros seccionales*)
  or industrial panels with all their exposed conductive parts connected to PE (ELEC-TAB-5), not for the TP of a dwelling, which requires an insulating
  Class II enclosure with the double-square symbol (ELEC-TAB-2). For outdoors or a meter pillar (*pilar*), check IP and UV protection on the data sheet.
- **Verify:** enclosure data sheet with the six data items; Class II symbol on the TP enclosure; blanking plates on free modules.
- **Don't:** use a junction box as a panel; use a metal enclosure as the TP; drill a Class II enclosure to
  run screws into the wall through the device space.
- **Source:** conextube.com, jeluz.net (Dinbox / Dinbox PRO / Dinbox IP item list), Schneider Catálogo Retail 2019
  p. 30, roker.com.ar; ELEC-TAB-2, ELEC-TAB-4, ELEC-TAB-5 and ELEC-TAB-7.

### ELEC-FAB-27: Terminal blocks (*borneras*), ferrules (*punteras*) and cable lugs: with a standard, of the right cross-section and with the manufacturer's tool
- **Rule:** feed-through terminals with **IEC 60947-7-1**, earth terminals with **IEC 60947-7-2**, fuse terminals with
  **IEC 60947-7-3** and compression lugs with **IEC 61238-1** (standards in the technical regulation), for the cross-section of the cable they
  receive. Ferrules (tubular terminals) and lugs are crimped with the crimping tool or die their manufacturer specifies
  for that cross-section.
- **Why:** a badly chosen or badly crimped terminal or lug is a contact resistance that heats up: it is one of the
  most common causes of burnt panels (ELEC-TAB-14). A lug squeezed with general-purpose pliers stays loose even if it "looks"
  tight.
- **How:** ask for the data sheet with minimum and maximum cross-section, current, voltage, tightening torque and crimping tool. Separate,
  identified neutral and earth terminal blocks (ELEC-TAB-15). Reference local manufacturer: Zoloda (Burzaco) declares
  its own design, tooling and production of terminal blocks, terminals and ferrules; its product standards were not read.
- **Verify:** firm tug on each crimped cable; no strand outside the ferrule; ferrule color or marking matches the
  cross-section; tightening torque from the data sheet.
- **Don't:** reuse ferrules or lugs; crimp with pliers; tin cable ends that go into screw terminals; use
  "hardware store" terminal blocks without a standard.
- **Source:** Res. SIyC 236/2024, Anexo II (text of Res. SIyC 26/2025), items 4.4.1 to 4.4.4 (feed-through, earth and
  fuse terminals, lugs) and 4.4.11 (terminal blocks, IEC 60998); zoloda.com.ar (consulted 2026-11-15); ELEC-TAB-14 and
  ELEC-TAB-15. **Not verified in a primary source:** technical data sheets of terminal blocks and ferrules from Zoloda or other brands (the
  ferrule color code varies with the system the manufacturer uses: check its table).

### ELEC-FAB-28: Insulating tape: with brand, standard and data on the roll, and only where it belongs
- **Rule:** buy insulating tape with **brand, standard, thickness, voltage or dielectric strength, and temperature** printed
  on the roll or packaging. It is for insulating and marking, not for replacing a properly made splice: splices are made with a terminal,
  connector or sleeve inside an accessible box.
- **Why:** a tape without data can come unstuck with the heat of the panel or the conduit and leave the copper exposed.
- **How:** usual technical reference for PVC tape with adhesive: IEC 60454-3-1. The technical regulation includes it among cable accessories
  with their own standard: item 4.4.6 of the current Anexo II, **IRAM-NM 60454-3-1, IRAM 2454 or IEC 60454** (ELEC-IRA-23), so
  it also carries conformity marking. Reference local manufacturer: Tacsa (Tecnología Argentina en Cintas S.A., Hurlingham), which declares it makes insulating
  and heat-shrink tapes; standards not published on the page consulted.
- **Verify:** data printed on the roll; splices inside boxes, not in the conduit.
- **Don't:** splice inside the conduit "with tape"; use packing tape or paper tape; use tape without data in a panel.
- **Source:** Res. SIyC 236/2024, Anexo II (text of Res. SIyC 26/2025), item 4.4.6 (insulating tapes: IRAM-NM
  60454-3-1 / IRAM 2454 / IEC 60454); IRAM catalog as per [iram-standards.md](iram-standards.md), ELEC-IRA-23 (IRAM-NM 60454-3-1
  ed. 1, 2012-09-28; IRAM 2454-1 to -3 ed. 1, 1989-11-03); tacsa.com.ar (consulted 2026-11-15). **Not verified in a primary
  source:** the text of IEC 60454-3-1 (paid standard).

## Earthing

| Brand | Company | Local manufacturing | Products | Declared standards |
|---|---|---|---|---|
| **Facbsa** (Fábrica Argentina de Conductores Bimetálicos S.A.) | Argentina, founded in 1984 (continuation of A.I.S.A., Copperweld representative since 1949) | Verified on its website: plant in the Parque Industrial Chimbas, San Juan, since 1985, by continuous electrodeposition | Copper-bonded steel earth rods (*jabalinas*) (ConduWeld line), earth rod clamps (*tomacables*), inspection boxes, Coppersteel exothermic welding, copper-clad steel cables and wires, aluminum-clad steel wire for rural electrification (MRT), lightning rods, soil enhancers | IRAM 2309 (earth rods), IRAM 2315 (exothermic welding), IRAM 2428 (lightning rods) |

Source: facbsa.com.ar (consulted 2026-11-15). Technical regulation standards for these products (Res. SIyC 236/2024, Anexo
II in the text of Res. SIyC 26/2025, items 4.6.2 to 4.6.7): copper-bonded steel earth rod IRAM 2309, galvanized steel IRAM 2310, electrochemical IRAM 2314, exothermic
welding IRAM 2315, copper-clad steel wire IRAM 2466 and stranded copper-clad steel conductors
IRAM 2467. **Not verified:** Cadweld / Erico (international exothermic welding brand; origin and local
distribution not verified), LCT (no documents found). Commercial earth rod sizes and installation criteria in
[earthing.md](earthing.md), ELEC-PAT-4.

### ELEC-FAB-17: Engraved IRAM earth rod (*jabalina*), clamp (*tomacable*) of its diameter, and buried joints welded or compressed
- **Rule:** the earth rod must be IRAM 2309 (copper-bonded steel) or IRAM 2310 (galvanized steel) with brand and standard engraved; the
  clamp must match the diameter of that earth rod; buried joints must be exothermic (IRAM 2315) or compression
  (ELEC-PAT-4).
- **Why:** a "copper" earth rod without a standard may be iron with a thin plating that corrodes in a few years: the
  earth resistance rises and the RCD (*diferencial*) stops protecting (ELEC-PAT-9).
- **How:** ask for the manufacturer's technical sheet (Facbsa publishes technical sheets and test reports on its website); check the
  engraving before driving it.
- **Verify:** IRAM engraving visible; inspection pit with access to the clamp (ELEC-PAT-5); measurement with an earth resistance tester
  (ELEC-PAT-10).
- **Don't:** buy earth rods without engraving; join with bolted terminals underground.
- **Source:** Res. SIyC 236/2024, Anexo II (text of Res. SIyC 26/2025), items 4.6.2, 4.6.3 and 4.6.5; facbsa.com.ar (declared standards, technical sheets,
  tests); ELEC-PAT-4; ELEC-IRA-13. **Not verified in a primary source:** the minimum copper thickness of IRAM 2309 (the
  manufacturers declare around 250 µm, see ELEC-PAT-4).

## Hazardous areas (explosive atmospheres)

### ELEC-FAB-29: In hazardous areas (*áreas clasificadas*), only material certified to IEC 60079 for that zone, and the design defines it
- **Rule:** in places with flammable gases, vapors or dusts (filling stations, paint booths, open battery
  rooms, silos, solvent stores) all electrical material must be certified to the
  **IEC 60079** series for the zone, gas or dust group, and temperature class defined by the design. The installer does not
  "eyeball" the zone.
- **Why:** an ordinary box, socket outlet or luminaire produces sparks or temperatures that ignite the atmosphere. Explosion-protected
  material only works if it is installed complete according to its certificate (cable glands, seals, covers, screw torque).
- **How:** ask the designer for the area classification in writing; ask for the data sheet and certificate of each device with its
  Ex marking (zone, group, T class); use the certified cable glands and accessories of the same system. Reference local
  manufacturer: **Delga S.A.** (Lomas de Zamora), which declares "fabricación propia" ("own manufacturing") of luminaires, boxes, control devices, signaling,
  socket outlets and plugs for hazardous areas "under IEC 60079 standards", with a plant audited by an IECEx body; the
  per-model certificates were not read for this edition. See also [special-installations.md](special-installations.md)
  (for example, the prohibition on installing EV chargers in hazardous areas).
- **Verify:** Ex marking of each device matches the zone on the drawing; certified cable glands; covers with all their
  screws.
- **Don't:** install ordinary "weatherproof IP65" material in a hazardous zone (IP is not Ex); replace an Ex cable gland with
  an ordinary one; open an Ex box while live.
- **Source:** delga.com (consulted 2026-11-15: "Fabricación propia", "normas IEC 60079", Sucre 1852, Lomas de Zamora);
  special-installations.md. **Not verified in a primary source:** the Argentine standard or regulation that requires
  area classification in each activity (fuels, industry) and the IECEx certificates of specific models.
## Emergency lighting and luminaires

| Brand | Verification status |
|---|---|
| Atomlux | Website not accessible (connection refused). Origin not verified in this edition |
| Gamasonic | Website blocked automated access. Origin not verified in this edition |
| Lumenac | Website with an expired TLS certificate. Origin not verified in this edition |
| Trivialtech | No documents found |

Source: attempts to access each brand's website on 2026-11-15; no product data verified.

### ELEC-FAB-18: Emergency lights (*luces de emergencia*): choose by autonomy, standard and test, not by brand
- **Rule:** ask for the data sheet with the **standard** (emergency luminaire IRAM-AADL J 2028-2-22 / IEC 60598-2-22, plus the general
  part IRAM-AADL J 2028-1), declared **autonomy** in hours, **emergency mode luminous flux**, battery type and
  recharge time, whether it is **maintained or non-maintained**, and conformity marking. The number and location are defined by the design
  (ELEC-EDI-16), which relies on IRAM-AADL J 2027 (ELEC-IRA-15).
- **Why:** real autonomy drops as the battery ages: a unit that declares neither autonomy nor emergency flux cannot be
  verified at approval or during maintenance.
- **How:** test the real autonomy at commissioning by cutting the circuit's supply and timing it; record it in
  the file and repeat it during maintenance.
- **Verify:** data sheet with standard, autonomy and flux; autonomy test recorded.
- **Don't:** use emergency lights without conformity marking; supply them from a socket outlet through a power strip (*zapatilla*); cite IRAM 2362
  (luminaire for incandescent lamps, 1985) as the standard for a current LED luminaire.
- **Source:** [iram-standards.md](iram-standards.md), ELEC-IRA-15 (IRAM catalog: IRAM-AADL J 2027 ed. 2, 2026-06-11; IRAM-AADL
  J 2028-2-22 ed. 2, 2025-04-22; IRAM-AADL J 2028-1 ed. 4, 2024-06-07); ELEC-EDI-16. **Not verified in a primary source:** the
  minimum autonomy required by each municipal code and the data of the brands listed.

## Measuring instruments

| Brand | Country of the parent company (not verified) | What is used on site |
|---|---|---|
| Chauvin Arnoux | France | Multifunction testers, megohmmeters, earth resistance testers |
| Fluke | United States | Multimeters, clamp meters, megohmmeters, installation testers |
| Hioki | Japan | Multimeters, clamp meters, megohmmeters, earth resistance testers |
| HT Instruments | Italy | Multifunction installation testers (IEC 61557) |
| Kyoritsu | Japan | Megohmmeters, earth resistance testers, RCD and loop testers, clamp meters |
| Megabras | Brazil | Earth resistance testers and megohmmeters |
| Megger | United Kingdom | Megohmmeters, earth resistance testers, multifunction testers |
| Metrel | Slovenia | Multifunction installation testers (IEC 61557) |
| Minipa | Brazil | Budget multimeters, clamp meters and megohmmeters |
| Sonel | Poland | Multifunction testers, megohmmeters, earth resistance testers |
| UNI-T | China | Budget multimeters, clamp meters, megohmmeters |

Source: **Not verified in a primary source** in this edition (parent company country from general knowledge; the factory of
each model may be elsewhere). We found no Argentine manufacturers of megohmmeters or earth resistance testers that we could document.
The list is not exhaustive: what matters is ELEC-FAB-19.

### ELEC-FAB-19: Instruments with the right measurement category, IEC 61010 / 61557 standards and current calibration
- **Rule:** to measure in panels use instruments with **category CAT III** as a minimum (CAT IV at the origin of the
  installation, meter pillar (*pilar*) and service connection (*acometida*)), according to IEC 61010, and for commissioning tests, instruments that comply with the
  relevant part of **IEC 61557** (insulation, continuity, earth, loop, RCDs). With a current calibration
  certificate.
- **Why:** a multimeter without a category can explode in your hand with a transient in the panel, and a measurement with an
  uncalibrated instrument is not valid in a test report (ELEC-MED-10).
- **How:** details in [testing-and-commissioning.md](testing-and-commissioning.md), ELEC-MED-13. The brand does not
  matter as much as the printed category, test leads of the same category, the accuracy declared in the manual, and the
  calibration.
- **Verify:** category printed on the instrument **and** on the test leads; calibration date.
- **Don't:** measure at the meter pillar with a CAT II multimeter; use test leads without a category with a CAT IV instrument.
- **Source:** ELEC-MED-13 and ELEC-SEG (IEC 61010 measurement categories, see [site-safety.md](site-safety.md)).

## When the client supplies the material, and when it turns out defective

### ELEC-FAB-20: If you install it, you answer for it: check it as if you had bought it yourself
- **Rule:** material bought by the client is checked with the same criteria (ELEC-FAB-1, -2, -6, -12, -21) before
  installing it. If it does not comply, report it in writing and do not install it.
- **Why:** the installation conformity declaration (DCI) or the installation certificate is signed by the installer or the
  professional, who declares that the materials are certified (ELEC-NOR-14).
- **How:** check marking and certificate, cable printing, Icn and type of the protective devices; if there are doubts about the cable,
  measure the length and the resistance (ELEC-FAB-21 and ELEC-FAB-7). Keep a record (photo of the marking, invoice) in the file.
- **Verify:** every item supplied by the client has its check record.
- **Don't:** install "because the client paid for it"; accept used materials from another job without checking them.
- **Source:** ELEC-NOR-14 and ELEC-NOR-16.

### ELEC-FAB-30: Defective or non-conforming material: warranty, written claim and complaint
- **Rule:** if a material turns out defective or does not comply (measures outside the standard, the certificate does not match, the coil comes
  short), **do not install it or remove it**, set the batch aside with its invoice, and file a written claim with the seller and the
  manufacturer or importer. If the product does not comply with the technical regulation, also report it to the authority.
- **Why:** Ley 24.240 (consumer protection law) gives a legal warranty of **6 months** from delivery for new movable goods (3 months for
  used ones), for defects that affect the match between what was offered and what was delivered, or correct operation, and makes
  producers, importers, distributors and sellers **jointly and severally liable**. A non-conforming product that
  stays on the market can burn the next job.
- **How:**
  1. Document: photos of the marking and the label, batch number, invoice, the measurement with an instrument, temperature and length
     (ELEC-FAB-7).
  2. Claim in writing (email with read receipt or a letter with a signed copy) to the seller and to the manufacturer or importer shown on
     the label and in the sworn declaration. Ask for replacement or refund.
  3. If it is a certification issue (no marking, certificate that does not match, fake QR code), notify the certification body
     shown on the certificate and the Secretaría de Industria y Comercio (Secretariat of Industry and Trade; authority for the technical regulation of Res. SIyC
     236/2024 and Disp. DNRT 2/2025).
  4. If the buyer is the end client and gets no answer, they can file a consumer complaint with the Defensa del
     Consumidor (consumer protection) office of their jurisdiction.
- **Verify:** claim with date and proof of sending in the file; batch set aside and labeled "no usar" ("do not use").
- **Don't:** install anyway "and claim later"; throw away the defective material before the claim is closed (it is the evidence).
- **Source:** Ley 24.240, arts. 11 (legal warranty: 6 months, 3 months for used goods) and 13 (joint and several liability), updated
  text at argentina.gob.ar/normativa (consulted 2026-11-15); Res. SIyC 236/2024 and Disp. DNRT 2/2025 (authority for the
  regulation). **Not verified in a primary source:** the current official channel for reporting a non-conforming electrical product
  to the Secretaría de Industria y Comercio (form, email or procedure) and the Defensa del Consumidor channel in each province;
  look them up on argentina.gob.ar before filing.

## Summary table by category

| Category | What to always require | Brands with data verified in this edition | Brands present, not verified |
|---|---|---|---|
| Fixed-installation cables | Conformity marking; printing with brand, standard, cross-section, voltage; resistance ≤ IEC 60228 maximum; real length | Prysmian (local manufacturing verified), Kalop (local manufacturing declared), Cimet (standards read in its technical sheets; plant not verified), Marlew (Argentine company; standards and plant not verified) | IMSA, Trefilcon, Epuyén, Fonseca |
| MCBs (*térmicas*) and RCDs (*diferenciales*) | IEC 60898-1 / 61008-1 / 61009-1; Icn on the front; type AC/A/F/B; certificate scheme 1b or 5 | Schneider (2026 data sheets and 2019 catalog), Jeluz (protection catalog; origin not verified) | ABB, Chint, Roker, Sica, Siemens, Steck, WEG, Zoloda |
| SPDs (*DPS*) and voltage protectors | IRAM 2345 / IEC 61643-11; type, Uc, Up, In; backup protection; protector that withstands 380 V | Schneider Easy9 SPD (2019 catalog) | Zoloda (SPD); voltage protectors: no data sheet read |
| Fuses and fuse bases | IEC 60269; same system and size; gG / aM | — | Zoloda (bases) |
| Contactors and motor protection circuit breakers (*guardamotores*) | IEC 60947-4-1 / 60947-2; category AC-1 / AC-3; coordination table | Jeluz (catalog; origin not verified) | Schneider, Siemens, ABB, WEG |
| Above 63 A | IEC 60947-2; Icu / Ics; selectivity; batch recorded | Schneider C120N (2019 catalog), Jeluz 80-125 A | — |
| Socket outlets, switches, plugs | IRAM 2071 earthed, 10/20 A; IRAM-NM 60884-1; switches IRAM-NM 60669-1; no universal socket outlets; plugs IRAM 2073 / 2063 | Kalop (IRAM 2071 10 and 20 A), Cambre, Jeluz and Richi (Argentine companies; standards not read), Schneider (switch rockers made in Florida in 2019) | Sica, Plasnavi |
| Conduits and boxes | Flame non-propagating; IRAM 62386 / IEC 61386 or IRAM 2005 / 2224 / 2205 for steel; boxes IRAM 2346 / 2353 / 62005 / 62224 or IEC 60670 | Kalop, Jeluz, Roker, Conextube | Genrod, Tubelectric, Daisa, Tecnocom |
| Enclosures | IEC 60670-24 / IRAM 62670 or IEC 62208; modules, IP, IK, Class II, dissipable power | Conextube, Jeluz, Roker, Schneider | Genrod, Steck |
| Terminal blocks, ferrules, lugs | IEC 60947-7-1 / -7-2 / -7-3; IEC 61238-1; crimping tool | Zoloda (local manufacturing declared; standards not read) | — |
| Insulating tape | Brand, standard and data on the roll | Tacsa (Argentine company, Hurlingham; no standards published on the page consulted) | — |
| Earthing | Engraved IRAM 2309 / 2310 earth rod (*jabalina*); IRAM 2315 welding or compression | Facbsa (local manufacturing verified on its website) | Cadweld / Erico, LCT |
| Hazardous areas | IEC 60079 certificate for the zone in the design | Delga (own manufacturing declared; per-model certificates not read) | — |
| Emergency lighting | IRAM-AADL J 2028-2-22 / IEC 60598-2-22; declared autonomy and flux | — | Atomlux, Gamasonic, Lumenac, Trivialtech |
| Instruments | IEC 61010 CAT III / IV; IEC 61557; calibration | — (origin not verified; we found no documented Argentine manufacturers) | Chauvin Arnoux, Fluke, Hioki, HT, Kyoritsu, Megabras, Megger, Metrel, Minipa, Sonel, UNI-T |

Source: the tables and rules of this document. "Verified" means we read it in a manufacturer's document or in a
certificate as of 2026-11-15, not that the brand is better than another.

## What this guide does not replace

- **The current data sheet and the certificate of the exact model.** Catalogs change; a figure from 2019 may not hold today.
  Before designing or signing, open the data sheet of the code you are going to buy.
- **The IRAM and IEC standards and the AEA Reglamentación (wiring regulations).** They are paid and are only cited here; for a design, consult them in their
  current edition (see [iram-standards.md](iram-standards.md) and [regulations-and-permits.md](regulations-and-permits.md)).
- **The current certification regime.** Resolutions and dispositions change; the details and dates are in
  ELEC-NOR-14, and what governs is the Boletín Oficial (official gazette).
- **Official unsafe product alerts.** A search on 2026-11-15 found no Argentine alerts about
  MCBs or cables; that does not mean there are none. Check argentina.gob.ar (Comercio, technical regulations and product
  alerts) before a large purchase.
- **A legal claim.** ELEC-FAB-30 summarizes the warranty under Ley 24.240; a specific dispute is resolved with advice
  and before the relevant body.
- **The judgment of the licensed professional (*profesional matriculado*)** who designs, directs and signs the installation, nor the inspection by the utility or
  the municipality.
- **A commercial recommendation.** This guide does not evaluate prices, lead times or customer service; it gives criteria to compare certified
  products with published data.
