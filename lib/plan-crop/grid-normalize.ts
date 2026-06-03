/** Mirror backend region_layout_compiler axis normalization (mm stations). */

const STATION_TOL_MM = 1;

export function dedupeSortStations(values: number[]): number[] {
  if (!values.length) return [];
  const cleaned = [...values].map((v) => Math.max(0, v)).sort((a, b) => a - b);
  const out: number[] = [];
  for (const v of cleaned) {
    if (!out.length || v - out[out.length - 1] > STATION_TOL_MM) {
      out.push(v);
    }
  }
  return out;
}

function positionsFromBaySpacings(bays: number[]): number[] {
  const positive = bays.filter((b) => b > STATION_TOL_MM);
  if (positive.length < 2) return [];
  const cumulative = [0];
  for (const bay of positive) {
    cumulative.push(cumulative[cumulative.length - 1] + bay);
  }
  return cumulative;
}

function strictlyIncreasingSubsequence(values: number[]): number[] {
  const seq = dedupeSortStations(values);
  if (!seq.length) return [];
  const out = [seq[0]];
  for (let i = 1; i < seq.length; i++) {
    if (seq[i] > out[out.length - 1] + STATION_TOL_MM) {
      out.push(seq[i]);
    }
  }
  return out;
}

/** Absolute stations or bay widths → cumulative stations from 0. */
export function normalizeAxisStations(values: number[]): number[] {
  const seq = dedupeSortStations(values);
  if (seq.length < 2) return seq;

  if (seq[0] <= STATION_TOL_MM) {
    const stations = strictlyIncreasingSubsequence(seq);
    if (stations.length >= 2) return stations;
  }

  const bays = seq.filter((v) => v > STATION_TOL_MM);
  if (bays.length >= 2) {
    const cumulative = positionsFromBaySpacings(bays);
    if (cumulative.length >= 2) return cumulative;
  }

  return seq;
}

function bestAxisCandidate(...candidateLists: number[][]): number[] {
  const normalized = candidateLists.filter((c) => c.length).map((c) => normalizeAxisStations(c));
  const isCumulative = (stations: number[]) =>
    stations.length >= 2 &&
    stations[0] <= STATION_TOL_MM &&
    stations.every((v, i) => i === 0 || v > stations[i - 1] + STATION_TOL_MM);

  const valid = normalized.filter(isCumulative);
  if (valid.length) {
    return valid.reduce((a, b) => (a.length >= b.length ? a : b));
  }
  if (normalized.length) {
    return normalized.reduce((a, b) => (a.length >= b.length ? a : b));
  }
  return [];
}

function expandSparseAxis(stations: number[], bays: number[]): number[] {
  if (stations.length >= 3) return stations;
  const positiveBays = bays.filter((b) => b > STATION_TOL_MM);
  if (positiveBays.length < 2) return stations;
  const fromBays = normalizeAxisStations(positionsFromBaySpacings(positiveBays));
  if (fromBays.length >= 3 && fromBays.length > stations.length) return fromBays;
  if (stations.length >= 2 && fromBays.length >= 2) {
    return bestAxisCandidate(stations, fromBays);
  }
  return stations.length >= 2 ? stations : fromBays;
}

/** Merge grid_lines / vision arrays; use bay chains only to fill sparse [0, total] grids. */
export function resolveGridStations(
  orderedLists: number[][],
  bayLists: number[][] = [],
): number[] {
  const stationCandidates = orderedLists.filter((c) => c.length > 0);
  const baysFlat = bayLists.flat().filter((b) => b > STATION_TOL_MM);

  if (!stationCandidates.length) {
    if (baysFlat.length >= 2) {
      return normalizeAxisStations(positionsFromBaySpacings(baysFlat));
    }
    return [];
  }

  const mergedRaw = stationCandidates.flat();
  const union = normalizeAxisStations(mergedRaw);
  const normalizedSources = stationCandidates.map((c) => normalizeAxisStations(c));
  const stations = bestAxisCandidate(union, ...normalizedSources);
  return expandSparseAxis(stations, baysFlat);
}
