# 建筑：真实拱窗、细分木地板、半木框架与保留中央净区的黑板。

def _cls_architecture_bevel(obj, width=.025, segments=2):
    # 小尺度倒角使轮廓保留手工模型的柔和高光。
    if width > 0:
        modifier = obj.modifiers.new('cls_手工倒角', 'BEVEL')
        modifier.width = width
        modifier.segments = segments
        modifier.limit_method = 'ANGLE'
    return obj


def _cls_x_prism(name, profile, x0, x1, mat, coll, bevel=0):
    # 沿 X 挤出任意 YZ 截面；拱窗墙体直接建模，不依赖布尔结果。
    n = len(profile)
    vertices = [(x0, y, z) for y, z in profile]
    vertices += [(x1, y, z) for y, z in profile]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    return _cls_architecture_bevel(mesh_obj(name, vertices, faces, mat, coll), bevel)


def _cls_timber_arch(name, y, angle_a, angle_b, mat, coll, low=False):
    # 每段梁都是实体矩形截面；后方仅留低短梁，中央不封顶。
    count = max(5, int(abs(angle_b - angle_a) * 16))
    spring = 3.13 if low else 4.47
    rise = .78 if low else 1.33
    vertices = []
    for i in range(count + 1):
        t = angle_a + (angle_b - angle_a) * i / count
        for radius_x, radius_z, offset_y in ((4.48, rise, -.13),
                                            (4.26, rise - .19, -.13),
                                            (4.48, rise, .13),
                                            (4.26, rise - .19, .13)):
            vertices.append((radius_x * math.cos(t), y + offset_y,
                             spring + radius_z * math.sin(t)))
    faces = [(0, 2, 3, 1)]
    for i in range(count):
        j, k = 4 * i, 4 * (i + 1)
        faces.extend([(j, k, k + 1, j + 1), (j + 2, j + 3, k + 3, k + 2),
                      (j, j + 2, k + 2, k), (j + 1, k + 1, k + 3, j + 3)])
    j = 4 * count
    faces.append((j, j + 1, j + 3, j + 2))
    return _cls_architecture_bevel(mesh_obj(name, vertices, faces, mat, coll), .025)


def build_architecture(M, C):
    coll = C['architecture']
    rng = random.Random(84021)
    # 悬浮剖面的厚底座与逐块铺设的错缝地板，正面不设墙体。
    box('cls_floor_foundation', (0, 0, -.23), (9.36, 11.36, .42), M['wood_dark'], coll, .12)
    box('cls_floor_lower_rim', (0, 0, -.43), (9.18, 11.18, .10), M['brass'], coll, .025)
    box('cls_floor_front_fascia', (0, -5.57, -.18), (9.34, .13, .35), M['wood'], coll, .035)
    box('cls_floor_right_fascia', (4.56, 0, -.18), (.13, 11.1, .35), M['wood'], coll, .035)
    plank_count = 0
    # 三十条窄板以 1.48 米为节距，交错半格接缝，总数超过二百。
    for row in range(30):
        x = -4.5 + (row + .5) * .3
        start = -5.5 - (.74 if row % 2 else 0)
        index = 0
        while start < 5.5:
            end = min(5.5, start + 1.48)
            lo = max(-5.5, start)
            length = end - lo
            if length > .06:
                y = (lo + end) / 2
                material = M['wood_light'] if rng.random() < .31 else M['wood']
                box('cls_floor_plank_%02d_%02d' % (row, index), (x, y, .015),
                    (.289, length - .014, .075), material, coll, .012)
                plank_count += 1
                if (row + index) % 4 == 0 and length > .4:
                    # 细长木纹采用低矮实体，避免大面积重复的贴图感。
                    grain_x = x + rng.uniform(-.085, .085)
                    tube('cls_floor_grain_%02d_%02d' % (row, index),
                         [(grain_x, lo + .12, .054),
                          (grain_x + .012, y, .055),
                          (grain_x - .008, end - .12, .054)],
                         .0028, M['wood_dark'], coll)
                if (row + index) % 3 == 0 and length > .35:
                    for k, nail_y in enumerate((lo + .075, end - .075)):
                        cylinder('cls_floor_pin_%02d_%02d_%d' % (row, index, k),
                                 (x + .085, nail_y, .055), .009, .006,
                                 M['metal'], coll, vertices=8)
            start += 1.48
            index += 1
    # 讲台高度较低，C1 占位区仍从台面以上获得完整净空。
    box('cls_stage_base', (0, 4.30, .085), (8.75, 2.40, .12), M['wood_dark'], coll, .045)
    for i in range(29):
        box('cls_stage_plank_%02d' % i, (-4.35 + (i + .5) * .3, 4.30, .1475),
            (.288, 2.36, .065), M['wood_light'] if i % 5 == 0 else M['wood'], coll, .012)
    box('cls_stage_front_nosing', (0, 3.1, .1175), (8.78, .10, .125), M['wood_light'], coll, .03)
    box('cls_stage_step', (0, 2.91, .075), (3.65, .36, .10), M['wood'], coll, .035)
    # 左墙下部为三层圆润砌石；所有窗洞从 1.10 米开始完全贯通。
    box('cls_left_lower_core', (-4.5, 0, .49), (.42, 11.0, .98), M['stone'], coll, .03)
    box('cls_front_lower_core', (0, 5.49, .49), (9.0, .42, .98), M['stone'], coll, .03)
    for wall in ('left', 'front'):
        span = 11.0 if wall == 'left' else 9.0
        for row in range(3):
            start = -span / 2 - (.41 if row % 2 else 0)
            index = 0
            while start < span / 2:
                end = min(span / 2, start + .82)
                lo = max(-span / 2, start)
                width = end - lo
                if width > .08:
                    center = (lo + end) / 2
                    z = .17 + row * .325 + rng.uniform(-.009, .009)
                    mat = M['rock_warm'] if rng.random() < .24 else M['stone']
                    if wall == 'left':
                        loc, size = (-4.475, center, z), (.52, width - .025, .30)
                    else:
                        loc, size = (center, 5.465, z), (width - .025, .52, .30)
                    box('cls_masonry_%s_%d_%02d' % (wall, row, index), loc, size, mat, coll, .045)
                start += .82
                index += 1
    box('cls_left_sill_rail', (-4.48, 0, 1.055), (.56, 11.07, .12), M['wood_dark'], coll, .024)
    box('cls_front_dado_rail', (0, 5.23, 1.055), (9.0, .12, .12), M['wood_dark'], coll, .024)
    # 前墙为连续抹灰板，左墙在窗洞外单独构建墙墩和拱上墙。
    box('cls_front_plaster', (0, 5.49, 2.8), (9.0, .40, 3.4), M['wall'], coll, .025)
    window_centers = (-2.8, .3, 3.4)
    radius, spring, wall_top = .975, 3.325, 4.5
    intervals = [(-5.5, window_centers[0] - radius)]
    intervals += [(window_centers[i] + radius, window_centers[i + 1] - radius) for i in range(2)]
    intervals.append((window_centers[-1] + radius, 5.5))
    for i, (a, b) in enumerate(intervals):
        box('cls_left_wall_pier_%d' % i, (-4.5, (a + b) / 2, 2.8),
            (.40, b - a, 3.4), M['wall'], coll, .012)
    for wi, center in enumerate(window_centers):
        # 上缘沿拱曲线取样，窗内没有用于伪装开口的深色平面。
        profile = []
        for j in range(33):
            angle = math.pi - math.pi * j / 32
            profile.append((center + radius * math.cos(angle), spring + radius * math.sin(angle)))
        profile += [(center + radius, wall_top), (center - radius, wall_top)]
        _cls_x_prism('cls_window_spandrel_%d' % wi, profile, -4.70, -4.30, M['wall'], coll)
        box('cls_window_sill_%d' % wi, (-4.46, center, 1.105), (.68, 2.24, .13), M['stone'], coll, .04)
        # 拱券与窗边立石独立分块，使每一块石头都有柔和的边缘。
        for j in range(13):
            a = math.pi * j / 13 + .009
            b = math.pi * (j + 1) / 13 - .009
            profile = [(center + r * math.cos(t), spring + r * math.sin(t))
                       for r, t in ((radius, a), (1.125, a), (1.125, b), (radius, b))]
            _cls_x_prism('cls_window_arch_stone_%d_%02d' % (wi, j), profile,
                         -4.76, -4.23, M['rock_warm'] if j % 4 == 0 else M['stone'], coll, .017)
        for side in (-1, 1):
            for j in range(6):
                h = (spring - 1.17) / 6
                box('cls_window_jamb_%d_%d_%d' % (wi, side, j),
                    (-4.49, center + side * 1.05, 1.17 + (j + .5) * h),
                    (.53, .15, h - .018), M['stone'], coll, .022)
        # 纤细木窗棂不会填满洞口，背后的天空可直接透过。
        rim = [(-4.275, center - .955, 1.18), (-4.275, center - .955, spring)]
        rim += [(-4.275, center + .955 * math.cos(math.pi - j * math.pi / 24),
                 spring + .955 * math.sin(math.pi - j * math.pi / 24)) for j in range(25)]
        rim += [(-4.275, center + .955, 1.18)]
        tube('cls_window_wood_rim_%d' % wi, rim, .035, M['wood_dark'], coll)
        box('cls_window_mullion_%d' % wi, (-4.278, center, 2.665), (.067, .055, 2.97), M['wood_dark'], coll, .012)
        box('cls_window_transom_%d' % wi, (-4.278, center, 3.18), (.067, 1.88, .05), M['wood_dark'], coll, .01)
        # 窗台前端的暖铜饰钉和左右小托臂。
        for side in (-1, 1):
            box('cls_window_sill_bracket_%d_%d' % (wi, side),
                (-4.19, center + side * .78, .945), (.18, .12, .23), M['wood'], coll, .025)
    # 木框架遵循墙墩布局，避免穿过三个真正的窗洞。
    for i, y in enumerate((-5.43, -1.25, 1.85, 5.40)):
        box('cls_left_timber_post_%d' % i, (-4.235, y, 2.80), (.17, .17, 3.42), M['wood_dark'], coll, .025)
        box('cls_left_post_cap_%d' % i, (-4.22, y, 4.40), (.26, .29, .13), M['wood_light'], coll, .025)
    box('cls_left_top_beam', (-4.23, 0, 4.49), (.21, 11.12, .20), M['wood_dark'], coll, .035)
    for i, x in enumerate((-4.36, -3.55, 2.65, 4.36)):
        box('cls_front_timber_post_%d' % i, (x, 5.245, 2.79), (.17, .15, 3.43), M['wood_dark'], coll, .025)
    box('cls_front_top_beam', (0, 5.245, 4.49), (9.12, .23, .22), M['wood_dark'], coll, .035)
    # 四道连续木拱构成无屋面的穹顶，颜色与室内承重木框架统一。
    for i, y in enumerate((-4.9, -2.2, 1.0, 4.94)):
        name = 'cls_roof_arch_front' if i == 3 else 'cls_roof_arch_full_%d' % i
        _cls_timber_arch(name, y, 0, math.pi, M['wood_dark'], coll)
    # 右侧纵向檩条连接拱脚，消除悬空的截断梁端。
    box('cls_roof_right_eave', (4.38, .02, 4.47), (.20, 10.10, .20), M['wood_dark'], coll, .025)
    # 右侧保留两根细支柱，右墙整体敞开。
    for i, (y, top) in enumerate(((4.94, 4.47), (-4.9, 4.47))):
        box('cls_right_open_post_%d' % i, (4.38, y, top / 2), (.19, .21, top), M['wood_dark'], coll, .028)
        box('cls_right_post_foot_%d' % i, (4.38, y, .19), (.31, .33, .31), M['stone'], coll, .055)
        box('cls_right_post_collar_%d' % i, (4.38, y, top - .10), (.28, .28, .15), M['brass'], coll, .025)
    # 前拱的横向细金属箍只位于梁上，不横穿室内视线。
    for i, angle in enumerate((.34, .86, math.pi / 2, math.pi - .86, math.pi - .34)):
        x = 4.37 * math.cos(angle)
        z = 4.47 + 1.23 * math.sin(angle)
        sphere('cls_arch_front_bolt_%d' % i, (x, 4.795, z), (.043, .018, .043), M['brass'], coll, segments=12, rings=6)
    log('建筑完成：%d 块地板，3 个真实拱窗，开放右墙/后墙/顶面。' % plank_count)


def _cls_board_text(name, value, x, z, size, material, coll, align='CENTER'):
    # 使用 Blender 内置字体，避免外部字体依赖；文字面朝室内负 Y。
    curve = bpy.data.curves.new(name + '_font', 'FONT')
    curve.body = value
    curve.size = size
    curve.align_x = align
    curve.align_y = 'CENTER'
    curve.extrude = 0
    curve.space_character = 1.12
    obj = bpy.data.objects.new(name, curve)
    coll.objects.link(obj)
    obj.parent = ROOM_ROOT
    obj.location = (x, 5.112, z)
    obj.rotation_euler = (math.pi / 2, 0, 0)
    curve.materials.append(material)
    return obj


def build_board(M, C):
    coll = C['architecture']
    cx, cy, cz = -.6, 5.20, 2.65
    width, height = 5.0, 2.15
    ui_width, ui_height = width * math.sqrt(.60), height * math.sqrt(.60)
    box('cls_board_back', (cx, cy + .025, cz), (5.29, .16, 2.44), M['wood_dark'], coll, .045)
    box('cls_board_chalk_surface', (cx, cy, cz), (width, .13, height), M['board'], coll, .014)
    # 中心独立面片精确占 60% 面积：材质、对象均有稳定名称供后续定位。
    x0, x1 = cx - ui_width / 2, cx + ui_width / 2
    z0, z1 = cz - ui_height / 2, cz + ui_height / 2
    panel = mesh_obj('cls_board_ui_panel', [(x0, 5.120, z0), (x1, 5.120, z0),
                                           (x1, 5.120, z1), (x0, 5.120, z1)],
                     [(0, 1, 2, 3)], M['board_ui'], coll)
    panel['ui_area_fraction'] = .60
    panel['ui_width'] = ui_width
    panel['ui_height'] = ui_height
    panel['clear_region'] = True
    # 粉笔痕、文字与符文全部约束在中央面片之外的边缘区域。
    for side in (-1, 1):
        x = cx + side * (width / 2 + .073)
        box('cls_board_frame_side_%d' % side, (x, 5.135, cz), (.145, .16, 2.45), M['wood'], coll, .023)
        box('cls_board_frame_side_inlay_%d' % side, (x, 5.045, cz), (.022, .012, 2.25), M['brass'], coll, .004)
    for side in (-1, 1):
        z = cz + side * (height / 2 + .074)
        box('cls_board_frame_horizontal_%d' % side, (cx, 5.135, z), (5.26, .16, .147), M['wood_light'], coll, .025)
        box('cls_board_frame_horizontal_inlay_%d' % side, (cx, 5.045, z), (5.06, .012, .022), M['brass'], coll, .004)
    box('cls_board_chalk_ledge', (cx, 4.985, 1.47), (5.38, .40, .105), M['wood'], coll, .025)
    box('cls_board_ledge_lip', (cx, 4.805, 1.505), (5.38, .055, .085), M['wood_light'], coll, .015)
    for i in range(4):
        cylinder('cls_board_chalk_%d' % i, (1.15 + i * .11, 4.985, 1.537), .016, .15,
                 M['paper'] if i < 3 else M['magic_lilac'], coll, vertices=10, rot=(0, math.pi / 2, -.13 * i))
    box('cls_board_eraser', (-2.61, 4.975, 1.56), (.28, .12, .09), M['wood_dark'], coll, .018)
    box('cls_board_eraser_felt', (-2.61, 4.975, 1.515), (.29, .13, .025), M['black'], coll, .006)
    # 左右各三枚小型阵法，圆弧半径与星芒都小于边缘带宽。
    for side in (-1, 1):
        x = cx + side * 2.205
        for i, z in enumerate((2.04, 2.65, 3.26)):
            for ri, radius in enumerate((.166, .192)):
                pts = [(x + radius * math.cos(j * math.tau / 32), 5.112,
                        z + radius * math.sin(j * math.tau / 32)) for j in range(32)]
                tube('cls_board_rune_circle_%d_%d_%d' % (side, i, ri), pts,
                     .0045 if ri else .006, M['paper'], coll, cyclic=True)
            count = 3 if i != 1 else 4
            pts = [(x + .137 * math.cos(math.pi / 2 + j * math.tau / count), 5.110,
                    z + .137 * math.sin(math.pi / 2 + j * math.tau / count)) for j in range(count)]
            tube('cls_board_rune_polygon_%d_%d' % (side, i), pts, .0055,
                 M['magic_lilac'] if i == 1 else M['paper'], coll, cyclic=True)
            tube('cls_board_rune_axis_%d_%d' % (side, i),
                 [(x - .07, 5.109, z), (x + .07, 5.109, z)], .004, M['paper'], coll)
            _cls_board_text('cls_board_rune_note_%d_%d' % (side, i),
                            ('I', 'II', 'III')[i], x, z - .252, .068, M['paper'], coll)
    _cls_board_text('cls_board_top_equation', 'L U M E N  +  A E T H E R   =   V I T A',
                    cx, 3.602, .09, M['paper'], coll)
    _cls_board_text('cls_board_bottom_equation', '01  /  INTENTIO     *     MOTUS     *     HARMONIA  /  03',
                    cx, 1.686, .075, M['paper'], coll)
    # 四个定位短线在净区外侧，中心区域绝无装饰跨越。
    for sx in (-1, 1):
        for sz in (-1, 1):
            x = cx + sx * (ui_width / 2 + .025)
            z = cz + sz * (ui_height / 2 + .025)
            tube('cls_board_ui_corner_%d_%d' % (sx, sz),
                 [(x + sx * .09, 5.111, z), (x, 5.111, z), (x, 5.111, z + sz * .065)],
                 .0045, M['magic_lilac'], coll)
    log('黑板完成：中心 UI %.5f × %.5f 米，占面板面积 60%%。' % (ui_width, ui_height))
    return panel


def _cls_backdrop_shadowless(material):
    # 阴影光线看到透明着色，天空与浮岛仍由原发光节点负责时段切换。
    nt = material.node_tree
    if nt.nodes.get('cls_backdrop_shadow_mix'):
        return
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    source = out.inputs['Surface'].links[0].from_socket
    light_path = nt.nodes.new('ShaderNodeLightPath')
    light_path.name = 'cls_backdrop_ray_type'
    transparent = nt.nodes.new('ShaderNodeBsdfTransparent')
    mix = nt.nodes.new('ShaderNodeMixShader')
    mix.name = 'cls_backdrop_shadow_mix'
    nt.links.new(light_path.outputs['Is Shadow Ray'], mix.inputs[0])
    nt.links.new(source, mix.inputs[1])
    nt.links.new(transparent.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    if hasattr(material, 'surface_render_method'):
        material.surface_render_method = 'DITHERED'
    if hasattr(material, 'use_transparent_shadow'):
        material.use_transparent_shadow = True
    if hasattr(material, 'shadow_method'):
        material.shadow_method = 'NONE'


def _cls_clip_window_polygon(polygon, aperture):
    # 用凸拱形逐边裁剪二维轮廓，所有背景岛屿都严格留在窗洞内部。
    result = list(polygon)
    for a, b in zip(aperture, aperture[1:] + aperture[:1]):
        if not result:
            break
        def distance(p):
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        previous = result[-1]
        dp = distance(previous)
        output = []
        for current in result:
            dc = distance(current)
            if (dc >= -1e-9) != (dp >= -1e-9):
                t = dp / (dp - dc)
                output.append((previous[0] + t * (current[0] - previous[0]),
                               previous[1] + t * (current[1] - previous[1])))
            if dc >= -1e-9:
                output.append(current)
            previous, dp = current, dc
        result = output
    return result


def build_backdrop(M, C):
    coll = C['backdrop']
    # 天空总网格只有三片拱窗大小的面，紧贴外墙，不在剖面外形成巨幅背景板。
    for key in ('backdrop_sky', 'backdrop_far', 'backdrop_island'):
        _cls_backdrop_shadowless(M[key])
    radius, spring, sill = .975, 3.325, 1.10
    apertures, vertices, faces = [], [], []
    for center in (-2.8, .3, 3.4):
        profile = [(center - radius, sill), (center + radius, sill), (center + radius, spring)]
        profile += [(center + radius * math.cos(j * math.pi / 32),
                     spring + radius * math.sin(j * math.pi / 32)) for j in range(1, 33)]
        apertures.append(profile)
        start = len(vertices)
        vertices.extend([(-4.705, y, z) for y, z in profile])
        faces.append(tuple(range(start, len(vertices))))
    sky = mesh_obj('cls_backdrop', vertices, faces, M['backdrop_sky'], coll)
    if hasattr(sky, 'visible_shadow'):
        sky.visible_shadow = False
    rng = random.Random(112)
    for wi, (center, aperture) in enumerate(zip((-2.8, .3, 3.4), apertures)):
        for layer, offset, top, width, depth in ((0, -.42, 3.20, .75, .64),
                                                (1, .44, 2.50, .65, .83),
                                                (2, -.30, 1.68, .46, .51)):
            cy = center + offset
            outline = [(cy - width, top), (cy - width * .65, top + .09),
                       (cy - width * .15, top + .13), (cy + width * .40, top + .08),
                       (cy + width, top), (cy + width * .55, top - .18),
                       (cy + width * .21, top - depth * .40), (cy + width * .06, top - depth),
                       (cy - width * .20, top - depth * .62), (cy - width * .60, top - .20)]
            material = M['backdrop_far'] if layer == 0 else M['backdrop_island']
            x = -4.702 + layer * .003
            clipped = _cls_clip_window_polygon(outline, aperture)
            if len(clipped) >= 3:
                ob = mesh_obj('cls_backdrop_island_%d_%d' % (wi, layer),
                              [(x, y, z) for y, z in clipped], [tuple(range(len(clipped)))], material, coll)
                if hasattr(ob, 'visible_shadow'):
                    ob.visible_shadow = False
            for ti in range(3):
                ty = cy + (ti - 1) * width * .45
                height = rng.uniform(.15, .28)
                zz = top + .08
                w = height * .28
                tree = [(ty - w, zz), (ty, zz + height), (ty + w, zz)]
                clipped = _cls_clip_window_polygon(tree, aperture)
                if len(clipped) >= 3:
                    ob = mesh_obj('cls_backdrop_tree_%d_%d_%d' % (wi, layer, ti),
                                  [(x + .001, y, z) for y, z in clipped], [tuple(range(len(clipped)))], material, coll)
                    if hasattr(ob, 'visible_shadow'):
                        ob.visible_shadow = False
    log('窗外背景完成：三片贴合真实窗洞的天空与裁剪浮岛，阴影光线透明。')
