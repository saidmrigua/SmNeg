<!-- SPDX-License-Identifier: Apache-2.0 | Copyright 2026 Said Mrigua -->
# Calibrating a film (ColorChecker on film)

A film profile makes the Scientific engine measure what it otherwise estimates: dye crosstalk, the
balance of the three dye layers and the film's contrast. One profile describes **one film stock on one
scanning set-up** (light source + camera). Make one per film you use.

## Without a chart: keep a roll's balance
The dye balance SMneg estimates is reliable on a full roll with varied subjects, and much less on a single
frame (grey chroma about 5.5 alone, 1.1–1.8 with a saved balance, on the synthetic model). After a good
roll: `FILM` → *Save this roll's colour balance as a film profile…* (at least 6 colour frames). Load it
later for short rolls or single frames of the same film on the same set-up. It holds the balance only: no
crosstalk correction, and the default contrast.

## Shoot the chart
1. ColorChecker Classic 24 (X-Rite / Calibrite), clean, flat.
2. Daylight (sun or overcast), even light, no glare on the patches. The chart about a third of the frame.
3. On the film you want to profile (for example Portra 400), three frames: normal, −1 and +1 stop.
4. Develop normally.

## Scan it
Same camera, light, lens and exposure method as your usual scans, flat field on. Include some clear
film (rebate) in the frame if you can, or pick it with `B`.

## Calibrate
1. Open the frame (Scientific engine), `FILM` → *Calibrate from a ColorChecker on this frame…*
2. Click the centres of the four corner patches (dark skin, bluish green, white, black), in any order.
   SMneg finds the chart's orientation itself.
3. Read the result (chart colour error before → after), name the profile, save. It is stored in
   `Documents/SmNeg/film_profiles/` and applied to the session.

Use the normal-exposure frame. `FILM` → *Load film profile…* reuses a profile on other rolls of the
same film, and *Automatic* returns to the roll estimate.
