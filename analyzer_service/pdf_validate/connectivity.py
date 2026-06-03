"""Connectivity heuristics for PDF vision / vector extraction quality."""

from __future__ import annotations

import math
from dataclasses import dataclass

from analyzer_service.schemas import PureSteelElementSpec, PureStructuralModelSpec


@dataclass
class ConnectivityReport:
    element_count: int
    cluster_count: int
    largest_cluster_size: int
    floating_endpoints: int
    span_x_mm: float
    span_y_mm: float
    span_z_mm: float

    @property
    def is_fragmented(self) -> bool:
        if self.element_count < 8:
            return True
        if self.cluster_count >= 3 and self.largest_cluster_size < self.element_count * 0.6:
            return True
        if self.floating_endpoints > max(4, self.element_count // 2):
            return True
        return False

    def summary(self) -> str:
        return (
            f"{self.element_count} segments, {self.cluster_count} disconnected cluster(s), "
            f"largest cluster {self.largest_cluster_size}, "
            f"{self.floating_endpoints} floating endpoint(s), "
            f"span {self.span_x_mm:.0f}×{self.span_y_mm:.0f}×{self.span_z_mm:.0f} mm"
        )


def _endpoints(el: PureSteelElementSpec) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    return (
        (float(el.start_x), float(el.start_y), float(el.start_z)),
        (float(el.end_x), float(el.end_y), float(el.end_z)),
    )


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def analyze_model_connectivity(
    model: PureStructuralModelSpec,
    *,
    join_tol_mm: float = 400.0,
) -> ConnectivityReport:
    elements = model.elements
    if not elements:
        return ConnectivityReport(0, 0, 0, 0, 0.0, 0.0, 0.0)

    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    nodes: list[tuple[float, float, float]] = []
    edges: list[tuple[int, int]] = []

    for el in elements:
        a, b = _endpoints(el)
        xs.extend((a[0], b[0]))
        ys.extend((a[1], b[1]))
        zs.extend((a[2], b[2]))
        ia = len(nodes)
        nodes.append(a)
        ib = len(nodes)
        nodes.append(b)
        edges.append((ia, ib))

    parent = list(range(len(nodes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if _dist(nodes[i], nodes[j]) <= join_tol_mm:
                union(i, j)

    clusters: dict[int, int] = {}
    for i in range(len(nodes)):
        root = find(i)
        clusters[root] = clusters.get(root, 0) + 1

    cluster_count = len(clusters)
    largest = max(clusters.values()) if clusters else 0

    floating = 0
    tol = join_tol_mm
    for i, pt in enumerate(nodes):
        hits = 0
        for j, other in enumerate(nodes):
            if i == j:
                continue
            if _dist(pt, other) <= tol:
                hits += 1
                break
        if hits == 0:
            floating += 1

    return ConnectivityReport(
        element_count=len(elements),
        cluster_count=cluster_count,
        largest_cluster_size=largest,
        floating_endpoints=floating,
        span_x_mm=max(xs) - min(xs) if xs else 0.0,
        span_y_mm=max(ys) - min(ys) if ys else 0.0,
        span_z_mm=max(zs) - min(zs) if zs else 0.0,
    )
