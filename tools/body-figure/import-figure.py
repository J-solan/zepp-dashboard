"""Genera ``frontend/src/workouts/bodyShapes.ts`` desde un set anatómico libre.

    python3 tools/body-figure/import-figure.py

Por qué se importa y ya no se dibuja: el body-map se dibujó a mano durante
varias rondas y no llegaba al listón (parecía un maniquí de piezas). El set de
`react-body-highlighter` (MIT, © 2020 GV79) es una lámina anatómica hecha por
un ilustrador, con las dos vistas, ambos lados y justo los grupos musculares
del vocabulario de ``ingest/muscle_map.toml``. Se importan SOLO las
coordenadas: el color por carga, la selección, el panel y los tests siguen
siendo nuestros.

Licencia y atribución en ``frontend/THIRD_PARTY.md``. Para re-importar:

    cd /tmp && npm pack react-body-highlighter@2.0.5 && tar xzf react-body-highlighter-2.0.5.tgz
    python3 tools/body-figure/import-figure.py /tmp/package/src/assets/index.ts

El fichero de origen declara polígonos (``svgPoints``: pares "x y" sueltos) en
un lienzo 100×200; aquí se convierten a ``path`` y se agrupan por músculo.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "frontend" / "src" / "workouts" / "bodyShapes.ts"
DEFAULT_SRC = Path(__file__).resolve().parent / "vendor" / "react-body-highlighter-assets.ts"

# Su vocabulario -> el nuestro (ingest/muscle_map.toml). Varios suyos caen en
# el mismo nuestro a propósito: los dos haces del deltoides son "hombro", y
# abdominales + oblicuos son "core", porque es como se reparte el volumen.
MUSCLES = {
    "trapezius": "trapecio",
    "upper-back": "dorsal",
    "lower-back": "lumbar",
    "chest": "pecho",
    "biceps": "biceps",
    "triceps": "triceps",
    "forearm": "antebrazo",
    "front-deltoids": "hombro",
    "back-deltoids": "hombro",
    "abs": "core",
    "obliques": "core",
    "adductor": "aductor",
    "abductors": "abductor",
    "hamstring": "femoral",
    "quadriceps": "cuadriceps",
    "calves": "gemelo",
    "left-soleus": "gemelo",
    "right-soleus": "gemelo",
    "gluteal": "gluteo",
}

# Piezas que no son músculo del vocabulario: se pintan en neutro, con el mismo
# trazo, para que la figura no aparezca decapitada.
NEUTRAL = {"head", "neck", "knees"}

# Manos y pies. El set de origen acaba en muñeca y tobillo; dibujarlos es
# nuestro y a 20 px de ancho no pasaban de guante y óvalo, así que la figura
# termina donde termina el set — como hacen otros body-maps. Para recuperarlos:
#   EXTREMITIES = (("antebrazo", hand, 5.0), ("gemelo", foot, 2.5))
EXTREMITIES: tuple = ()


def parse(source: str, name: str):
    """[(slug, [polígono, ...])] del array ``name`` del fichero de origen."""
    block = re.search(rf"export const {name}[^=]*=\s*\[(.*?)\n\];", source, re.S)
    if block is None:
        raise SystemExit(f"no encuentro {name} en el fichero de origen")
    out = []
    for entry in re.finditer(
        r"muscle:\s*MuscleType\.(\w+),\s*svgPoints:\s*\[(.*?)\]", block.group(1), re.S
    ):
        const, points = entry.group(1), entry.group(2)
        slug = SLUGS[const]
        out.append((slug, [p for p in re.findall(r"'([^']+)'", points)]))
    return out


def parse_points(points: str):
    nums = [float(n) for n in points.split()]
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]


def fmt(p) -> str:
    return f"{round(p[0], 2):g},{round(p[1], 2):g}"


def to_path(pts, radius=1.1) -> str:
    """Polígono -> contorno con las ESQUINAS redondeadas.

    Ojo con la alternativa evidente (curva por los puntos medios): suaviza
    más, pero mete cada forma hacia dentro. Al hacerlo, dos músculos que en el
    set comparten frontera se separan, la figura se deshace en tiras sueltas y
    desaparecen las líneas continuas entre grupos. Redondear solo las esquinas
    respeta los bordes: los vecinos se siguen tocando y sus trazos forman una
    sola red blanca.
    """
    n = len(pts)
    out = []
    for i in range(n):
        prev, cur, nxt = pts[i - 1], pts[i], pts[(i + 1) % n]
        a = _towards(cur, prev, radius)
        b = _towards(cur, nxt, radius)
        out.append(("M" if i == 0 else "L") + fmt(a))
        out.append(f"Q{fmt(cur)} {fmt(b)}")
    return " ".join(out) + " Z"


def _towards(origin, target, dist):
    """Punto a ``dist`` de ``origin`` hacia ``target``, sin pasar de la mitad
    del lado (si no, un lado corto se comería el de al lado)."""
    dx, dy = target[0] - origin[0], target[1] - origin[1]
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    k = min(dist / length, 0.5)
    return (origin[0] + dx * k, origin[1] + dy * k)


def blob(cx, cy, w, h, tilt=0.0):
    """Forma redondeada para las piezas que el set no trae (manos y pies).
    ``tilt`` inclina la base hacia fuera, que es como cae una mano relajada."""
    pts = [
        (cx - w / 2, cy),
        (cx - w / 2 - tilt * 0.3, cy + h * 0.45),
        (cx - w / 2 * 0.7 - tilt, cy + h),
        (cx + w / 2 * 0.7 - tilt, cy + h),
        (cx + w / 2 - tilt * 0.3, cy + h * 0.45),
        (cx + w / 2, cy),
    ]
    return pts


def by_side(polys):
    """Agrupa polígonos por lado del lienzo (x<50 / x>=50)."""
    sides: dict[str, list] = {}
    for poly in polys:
        key = "L" if sum(x for x, _ in poly) / len(poly) < 50 else "R"
        sides.setdefault(key, []).append(poly)
    return list(sides.values())


def shorten(pts, factor):
    """Acorta un polígono hacia su extremo SUPERIOR. El antebrazo del set es
    casi tan largo como todo el brazo y al lado del bíceps parecía otro
    miembro; el codo (arriba) no se mueve, solo sube la muñeca."""
    top = min(y for _, y in pts)
    return [(x, top + (y - top) * factor) for x, y in pts]


def wrist(poly, band=6.0):
    """Centro y dirección del corte final de un miembro (muñeca o tobillo).

    Se toman los vértices dentro de ``band`` del punto más bajo: son los dos
    extremos del borde de corte. Su punto medio es el centro real de la muñeca
    y su perpendicular, la dirección en la que cuelga la mano. Con el mero
    "punto más bajo" la mano se colgaba del pico interior — que es justo lo que
    pasaba en la vista posterior, donde ese corte va muy diagonal.
    """
    bottom = max(y for _, y in poly)
    edge = [p for p in poly if p[1] >= bottom - band]
    if len(edge) < 2:
        edge = sorted(poly, key=lambda p: -p[1])[:2]
    lo = min(edge, key=lambda p: p[0])
    hi = max(edge, key=lambda p: p[0])
    cx0, cy0 = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    ex, ey = hi[0] - lo[0], hi[1] - lo[1]
    length = (ex * ex + ey * ey) ** 0.5 or 1.0
    # Perpendicular al corte, apuntando hacia fuera del miembro.
    ax, ay = -ey / length, ex / length
    if ay < 0:
        ax, ay = -ax, -ay
    return (cx0, cy0), (ax, ay)


def extremes(polygons, take=4):
    """Centro del BORDE BAJO de cada lado (x<50 / x>=50) y su ancho.

    Colgar la mano del vértice más bajo la dejaba descentrada y fuera del
    brazo: un polígono acaba en punta y ese vértice no es el centro de la
    muñeca. Se promedian los ``take`` puntos más bajos, que sí lo son.
    """
    sides: dict[str, list] = {}
    for pts in polygons:
        for x, y in pts:
            sides.setdefault("L" if x < 50 else "R", []).append((x, y))
    out = {}
    for key, pts in sides.items():
        low = sorted(pts, key=lambda p: -p[1])[:take]
        xs = [p[0] for p in low]
        out[key] = ((min(xs) + max(xs)) / 2, max(p[1] for p in low), max(max(xs) - min(xs), 4.5))
    return out


HEADER = '''// Figura del body-map: lámina anatómica de dos vistas.
//
// IMPORTADO, NO DIBUJADO A MANO. Origen: `react-body-highlighter` v2.0.5
// (MIT, © 2020 GV79) — ver `frontend/THIRD_PARTY.md`. Se regenera con
// `python3 tools/body-figure/import-figure.py`; no editar a mano.
//
// El cuerpo ES los músculos: no hay silueta de fondo. Cada región trae sus dos
// lados (el set ya es simétrico), así que aquí no se refleja nada.
'''


def ts_list(values, indent=""):
    inner = ",\n".join(f"{indent}  '{v}'" for v in values)
    return "[\n" + inner + f",\n{indent}]"


def hull(polys):
    """Envolvente convexa de varios polígonos (monotone chain).

    El set parte antebrazo y tríceps en dos lonchas por lado; a tamaño de
    tarjeta son dos tiras paralelas que no se leen como un músculo. Unidas en
    una sola forma sí.
    """
    pts = sorted({(round(x, 3), round(y, 3)) for poly in polys for x, y in poly})
    if len(pts) <= 2:
        return list(pts)

    def half(points):
        out = []
        for p in points:
            while len(out) >= 2:
                (x1, y1), (x2, y2) = out[-2], out[-1]
                if (x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1) > 0:
                    break
                out.pop()
            out.append(p)
        return out[:-1]

    return half(pts) + half(pts[::-1])


def clip_band(poly, top, bottom):
    """Recorta un polígono a la banda horizontal [top, bottom]
    (Sutherland-Hodgman con dos semiplanos)."""
    def cut(pts, keep, edge_y):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            cur_in, prev_in = keep(cur[1], edge_y), keep(prev[1], edge_y)
            if cur_in != prev_in:
                t = (edge_y - prev[1]) / (cur[1] - prev[1])
                out.append((prev[0] + (cur[0] - prev[0]) * t, edge_y))
            if cur_in:
                out.append(cur)
        return out

    band = cut(poly, lambda y, e: y >= e, top)
    return cut(band, lambda y, e: y <= e, bottom) if band else []


def cx(poly):
    """Centro horizontal de un polígono."""
    xs = [x for x, _ in poly]
    return (min(xs) + max(xs)) / 2


def span_at(poly, y):
    """[x_min, x_max] del polígono a la altura ``y``."""
    xs = []
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 - y) * (y2 - y) <= 0 and y1 != y2:
            xs.append(x1 + (x2 - x1) * (y - y1) / (y2 - y1))
    return (min(xs), max(xs)) if xs else None


def ab_blocks(poly, weights=(0.24, 0.28, 0.48), gap=1.0, dip=1.4):
    """Tres bloques del recto abdominal, de arriba a abajo.

    ``weights`` reparte la altura: los de arriba cortos y el de abajo el doble,
    que es como se ve un abdomen. El borde inferior no es recto: se hunde
    ``dip`` en el centro, porque un cuadrado perfecto canta a rejilla.
    """
    ys = [y for _, y in poly]
    top, bottom = min(ys), max(ys)
    height = bottom - top
    out = []
    cursor = top
    for i, w in enumerate(weights):
        y0 = cursor + (gap if i else 0.6)
        y1 = cursor + w * height - gap / 2
        cursor += w * height
        a, b = span_at(poly, y0), span_at(poly, y1)
        if not a or not b:
            continue
        mid = ((b[0] + b[1]) / 2, y1 - dip)
        out.append([(a[0], y0), (a[1], y0), (b[1], y1), mid, (b[0], y1)])
    return out


def segments(poly, n):
    """Parte el polígono en ``n`` bloques horizontales con una junta entre
    ellos: es lo que convierte la plancha del abdomen en cuadraditos."""
    ys = [y for _, y in poly]
    top, bottom = min(ys), max(ys)
    step = (bottom - top) / n
    out = []
    for i in range(n):
        piece = clip_band(poly, top + i * step + (0.6 if i else 0), top + (i + 1) * step - 0.6)
        if len(piece) >= 3:
            out.append(piece)
    return out


def move(poly, dx=0.0, dy=0.0):
    return [(x + dx, y + dy) for x, y in poly]


def scale(poly, sx=1.0, sy=1.0, ox=50.0, oy=None):
    """Escala respecto a (ox, oy); ``oy`` por defecto es el borde superior."""
    if oy is None:
        oy = min(y for _, y in poly)
    return [(ox + (x - ox) * sx, oy + (y - oy) * sy) for x, y in poly]


def axis(polys):
    """Dirección del miembro: del centro de su mitad alta al de la baja. Sirve
    para colgar la mano y el pie EN LÍNEA con el brazo o la pierna, que caen en
    diagonal; si no, quedan pegados de lado."""
    pts = [p for poly in polys for p in poly]
    ys = [y for _, y in pts]
    mid = (min(ys) + max(ys)) / 2
    hi = [p for p in pts if p[1] <= mid] or pts
    lo = [p for p in pts if p[1] > mid] or pts
    ax = sum(x for x, _ in lo) / len(lo) - sum(x for x, _ in hi) / len(hi)
    ay = sum(y for _, y in lo) / len(lo) - sum(y for _, y in hi) / len(hi)
    # A medias con la vertical: con el giro completo la mano sale en diagonal
    # y parece una paleta; una mano relajada cuelga casi a plomo.
    ax *= 0.45
    length = (ax * ax + ay * ay) ** 0.5 or 1.0
    return ax / length, ay / length


def rotate(pts, cx0, cy0, ax, ay):
    """Gira los puntos para que su eje vertical apunte en (ax, ay)."""
    for x, y in pts:
        dx, dy = x - cx0, y - cy0
        yield (cx0 + dx * ay - dy * ax, cy0 + dx * ax + dy * ay)


def hand(x, y, w=10.5, h=18.0, inward=1.0):
    """Mano relajada colgando, vista de frente.

    A tamaño de tarjeta una mano solo se lee por tres cosas: que sea más larga
    que ancha, que tenga pulgar y que se le note UNA separación de dedos. Todo
    lo demás se pierde, así que no se dibuja.
    """
    # -0.12 centra la silueta en el ancla: los puntos van de -0.24 a +0.48
    # (el pulgar tira hacia dentro) y sin corregirlo la mano queda desviada.
    f = lambda dx, dy: (x + (dx - 0.12) * w * inward, y + dy * h)
    return [
        f(-0.24, 0.00),   # muñeca, borde externo
        f(-0.38, 0.24),
        f(-0.44, 0.56),   # nudillos
        f(-0.40, 0.80),
        f(-0.28, 0.95),   # meñique
        f(-0.12, 1.00),
        f(-0.04, 0.88),   # muesca entre dedos
        f(0.06, 0.98),
        f(0.22, 0.90),    # índice
        f(0.31, 0.66),
        f(0.46, 0.46),    # pulgar
        f(0.48, 0.30),
        f(0.33, 0.18),
        f(0.24, 0.00),    # muñeca, borde interno
    ]


def foot(x, y, w=18.0, h=10.0, outward=1.0):
    """Pie de frente: talón estrecho arriba, arco marcado por dentro y puntera
    ancha girada hacia fuera. Muy apaisado a propósito — cuadrado se lee como
    una bola, que es lo que pasaba antes."""
    f = lambda dx, dy: (x + dx * w * outward, y + dy * h)
    return [
        f(-0.16, 0.00),   # talón, lado interno
        f(-0.24, 0.40),
        f(-0.20, 0.72),   # arco
        f(-0.06, 0.94),
        f(0.14, 1.00),    # dedos
        f(0.38, 0.94),
        f(0.52, 0.72),    # puntera
        f(0.50, 0.42),
        f(0.30, 0.14),
        f(0.12, 0.00),    # talón, lado externo
    ]



def view_box(polygons, margin=3.0):
    """Lienzo ajustado a ESTA vista. Con uno común, la vista posterior (que
    llega más abajo) salía más larga que la frontal y las dos figuras no
    quedaban a la misma altura."""
    xs = [x for pts in polygons for x, _ in pts]
    ys = [y for pts in polygons for _, y in pts]
    x0, y0 = min(xs) - margin, min(ys) - margin
    return f"{x0:g} {y0:g} {max(xs) - x0 + margin:g} {max(ys) - y0 + margin:g}"


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    source = src.read_text(encoding="utf-8")

    global SLUGS
    SLUGS = dict(re.findall(r"(\w+):\s*'([a-z-]+)'", source)) or {}
    # El enum `MuscleType` vive en otro fichero del paquete; se vendoriza al
    # lado del de formas.
    meta = src.parent / "metadata.ts"
    if meta.exists():
        SLUGS |= dict(re.findall(r"(\w+):\s*'([a-z-]+)'", meta.read_text(encoding="utf-8")))

    # El componente de origen declara 100x200 pero sus polígonos llegan a y=220
    # (los pies): con 200 se cortarían, así que el lienzo real es 100x220.
    parts = [HEADER]
    head_front = None
    for name, view in (("anteriorData", "FRONT"), ("posteriorData", "BACK")):
        groups: dict[str, list] = {}
        neutral: list = []
        for slug, polygons in parse(source, name):
            polys = [parse_points(p) for p in polygons]

            # El sóleo del set baja hasta y=220 en dos lonchas larguísimas: no
            # se quita (es la inserción baja del gemelo), se acorta y se
            # ensancha para que remate el gemelo en vez de colgar como un palo.
            if slug in ("left-soleus", "right-soleus"):
                # Remate del gemelo: se acorta, se ensancha y sube con el resto
                # del grupo (llegaba hasta el tobillo y el gemelo parecía
                # ocupar toda la pierna).
                polys = [move(scale(p, sx=1.4, sy=0.78, ox=cx(p)), dy=-5) for p in polys]

            if slug == "head":
                # La cabeza del set es distinta en cada vista (un óvalo delante,
                # un octógono detrás) y el salto canta al cambiar de vista: se
                # usa la frontal en las dos.
                head_front = head_front or polys
                neutral += head_front
                continue
            if slug in NEUTRAL:
                neutral += polys
                continue
            if slug not in MUSCLES:
                raise SystemExit(f"grupo sin mapear: {slug}")

            if slug == "forearm":
                # De frente se dejan las DOS masas por lado (flexora y
                # extensora); de espaldas, una sola. En ambos casos algo más
                # corto: al lado del bíceps parecía otro miembro.
                if view == "BACK":
                    polys = [hull(side) for side in by_side(polys)]
                polys = [shorten(p, 0.86) for p in polys]
            elif slug == "triceps" and view == "FRONT":
                # De frente no se ve el tríceps: su trozo se suma al bíceps,
                # que así ocupa el brazo entero en vez de media caña.
                groups.setdefault("biceps", []).extend(polys)
                continue
            elif slug == "triceps":
                polys = [hull(side) for side in by_side(polys)]
            elif slug == "abs":
                # Seis cuadritos: tres por lado. Los de arriba, cortos; el
                # último, el doble de largo, y todos con el borde inferior
                # ligeramente cóncavo, como un abdomen de verdad.
                polys = [seg for poly in polys for seg in ab_blocks(poly)]
            elif slug == "hamstring":
                # Un vientre por lado: el set lo parte en lonchas y a este
                # tamaño se leían como cuchillas sueltas y en punta.
                polys = [hull(side) for side in by_side(polys)]
            elif slug == "calves":
                # Suben MUY poco: la rodilla es una pieza fija justo encima y
                # con 10 de subida los gemelos se le montaban, dejándola
                # incrustada en medio de la pierna. Y se recortan un pelo por
                # abajo para dejarle sitio al remate, que iba demasiado justo.
                polys = [move(scale(p, sx=0.96, sy=0.9), dy=-3) for p in polys]
            elif slug == "adductor":
                # Algo más alto para que no quede un rombo flotando entre las
                # piernas: así llega al glúteo por arriba y al muslo por abajo.
                polys = [scale(p, sx=1.05, sy=1.18) for p in polys]
            elif slug == "upper-back":
                # Dorsal más ancho y algo más largo: es lo que le da forma de V.
                polys = [scale(p, sx=1.12, sy=1.1) for p in polys]

            groups.setdefault(MUSCLES[slug], []).extend(polys)

        if view == "FRONT":
            groups["biceps"] = [hull(side) for side in by_side(groups["biceps"])]

        # El set acaba en muñeca y tobillo. Manos y pies se añaden aquí como
        # piezas neutras, colgadas del punto más bajo del antebrazo y de la
        # pierna, para que la figura no termine en muñón.
        soft: list = []
        for member, build, back in EXTREMITIES:
            for side in ("L", "R"):
                polys = [p for p in groups[member] if (cx(p) < 50) == (side == "L")]
                if not polys:
                    continue
                # El polígono que baja más es el que acaba en la muñeca (o el
                # tobillo); los demás del grupo mueren antes.
                low = max(polys, key=lambda poly: max(y for _, y in poly))
                (wx, wy), (ax, ay) = wrist(low)
                # Se retrocede POR EL EJE para solapar el corte, y se construye
                # y gira sobre el MISMO punto: hacerlo sobre puntos distintos
                # era lo que descuadraba la mano del antebrazo.
                ox, oy = wx - ax * back, wy - ay * back
                pts = (
                    build(ox, oy, inward=1.0 if side == "L" else -1.0)
                    if build is hand
                    else build(ox, oy, outward=1.0 if side == "L" else -1.0)
                )
                soft.append(list(rotate(pts, ox, oy, ax, ay)))

        every = neutral + soft + [p for polys in groups.values() for p in polys]
        parts.append(f"\nexport const VIEW_BOX_{view} = '{view_box(every)}'")
        # Manos y pies con redondeo fino: con el de los músculos (1.1) se
        # perdían el pulgar y los dedos y volvían a ser muñones.
        paths = [to_path(p) for p in neutral] + [to_path(p, 0.45) for p in soft]
        parts.append(f"\nexport const NEUTRAL_{view} = {ts_list(paths)}")
        lines = [f"\nexport const {view} = {{"]
        for muscle, polys in groups.items():
            lines.append(f"  {muscle}: {ts_list([to_path(p) for p in polys], '  ')},")
        lines.append("}")
        parts.append("\n".join(lines))
    parts.append("")

    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"escrito {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
