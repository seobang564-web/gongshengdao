# 家具、书籍与悬浮教具。所有尺寸为米；不依赖外部资源。
# 这段与基础工具拼接；每个动态道具保留独立根节点以便投影避让。


def _cls_prop_parent(ob, root):
    basis = ob.matrix_basis.copy()
    ob.parent = root
    ob.matrix_parent_inverse = Matrix.Identity(4)
    ob.matrix_basis = basis
    return ob


def _cls_prop_box(name, loc, size, mat, coll, root=None, bevel=.025, rot=(0, 0, 0)):
    ob = box(name, loc, size, mat, coll, bevel=bevel, rot=rot)
    for mod in ob.modifiers:
        if mod.type == 'BEVEL':
            mod.segments = 2 if min(size) > .065 else 1
    return _cls_prop_parent(ob, root) if root else ob


def _cls_prop_sphere(name, loc, size, mat, coll, root=None, segments=16, rings=8):
    ob = sphere(name, loc, size, mat, coll, segments=segments, rings=rings)
    return _cls_prop_parent(ob, root) if root else ob


def _cls_prop_tube(name, points, radius, mat, coll, root=None, cyclic=False):
    ob = tube(name, points, radius, mat, coll, cyclic=cyclic)
    ob.data.bevel_resolution = 1 if radius >= .008 else 0
    return _cls_prop_parent(ob, root) if root else ob


def _cls_prop_cyl(name, loc, radius, depth, mat, coll, root=None,
                  vertices=20, rot=(0, 0, 0), radius2=None):
    ob = cylinder(name, loc, radius, depth, mat, coll,
                  vertices=vertices, rot=rot, radius2=radius2)
    for mod in ob.modifiers:
        if mod.type == 'BEVEL':
            mod.segments = 1
    return _cls_prop_parent(ob, root) if root else ob


def _cls_prop_multibox(name, blocks, materials, coll, bevel=.006):
    """一本书合并成单网格，全部书架实例共享少量网格。"""
    verts, faces, indices = [], [], []
    for center, size, material_index in blocks:
        x, y, z = center
        a, b, c = (v * .5 for v in size)
        n = len(verts)
        verts.extend([(x-a, y-b, z-c), (x+a, y-b, z-c),
                      (x+a, y+b, z-c), (x-a, y+b, z-c),
                      (x-a, y-b, z+c), (x+a, y-b, z+c),
                      (x+a, y+b, z+c), (x-a, y+b, z+c)])
        faces.extend([tuple(n+j for j in f) for f in
                      [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                       (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]])
        indices.extend([material_index] * 6)
    ob = mesh_obj(name, verts, faces, materials[0], coll)
    for mat in materials[1:]:
        ob.data.materials.append(mat)
    for polygon, index in zip(ob.data.polygons, indices):
        polygon.material_index = index
    if bevel:
        mod = ob.modifiers.new('cls_soft_book_edges', 'BEVEL')
        mod.width, mod.segments = bevel, 1
        # 封皮与纸块倒角，极小的烫金细带保持平直，共享实例更轻巧。
        mod.limit_method = 'WEIGHT'
        weights = ob.data.attributes.new('bevel_weight_edge', 'FLOAT', 'EDGE')
        for edge in ob.data.edges:
            weights.data[edge.index].value = 1.0 if edge.vertices[0] < 32 else 0.0
    return ob


def _cls_book_source(name, cover, M, coll):
    # 原点在书底，脊背朝 -Y；书架旋转后朝教室内。
    blocks = [((0, 0, .215), (.104, .255, .405), 0),
              ((-.061, 0, .215), (.018, .282, .43), 1),
              (( .061, 0, .215), (.018, .282, .43), 1),
              ((0, -.135, .215), (.139, .024, .43), 1)]
    for z in (.063, .101, .328, .367):
        blocks.append(((0, -.151, z), (.143, .013, .011), 2))
    blocks.append(((0, -.153, .234), (.080, .010, .071), 2))
    blocks.append(((0, -.160, .234), (.056, .005, .047), 1))
    return _cls_prop_multibox(name, blocks, [M['paper'], cover, M['brass']], coll)


def _cls_book_instance(source, name, coll, root, loc, scale=(1, 1, 1), rz=0, lean=0):
    ob = source.copy()
    ob.data = source.data
    ob.name = name if name.startswith('cls_') else 'cls_' + name
    coll.objects.link(ob)
    ob.parent = root
    ob.location = loc
    ob.rotation_euler = (0, lean, rz)
    ob.scale = scale
    return ob


def _cls_open_book(name, pos, scale, angle, M, coll, cover='book_red', root=None):
    """弧形书页、分层纸边和非文字符号；页面厚度无需细分修改器。"""
    book = empty(name + '_root', pos, coll)
    if root:
        _cls_prop_parent(book, root)
    book.scale = (scale, scale, scale)
    book.rotation_euler.z = angle
    _cls_prop_box(name + '_left_cover', (-.172, 0, .017), (.345, .46, .028),
                  M[cover], coll, book, .018, (0, -.065, 0))
    _cls_prop_box(name + '_right_cover', (.172, 0, .017), (.345, .46, .028),
                  M[cover], coll, book, .018, (0, .065, 0))
    _cls_prop_cyl(name + '_spine', (0, 0, .029), .028, .465, M[cover], coll,
                  book, vertices=16, rot=(math.pi/2, 0, 0))
    def surface(u, side, y, lift=0):
        return (side * (.018 + .313*u), y,
                .053 + .030*math.sin(math.pi*u) + .012*u + lift)
    for side in (-1, 1):
        verts, faces = [], []
        for row in range(2):
            for i in range(13):
                verts.append(surface(i / 12, side, -.211 if row == 0 else .211))
        for i in range(12):
            face = (i, i+1, i+14, i+13)
            faces.append(face if side == 1 else tuple(reversed(face)))
        page = mesh_obj(name + '_curved_page_' + str(side), verts, faces, M['paper'], coll)
        _cls_prop_parent(page, book)
        solid = page.modifiers.new('cls_paper_block_thickness', 'SOLIDIFY')
        solid.thickness = .024
        for poly in page.data.polygons:
            poly.use_smooth = True
        for j in range(3):
            for yy in (-.212, .212):
                points = [surface(i/12, side, yy, -.006-j*.007) for i in range(13)]
                _cls_prop_tube(name + '_layered_page_edge', points, .0018,
                               M['wood_light'], coll, book)
        # 细短行、圆形符文以及三角星图，避免依赖字体。
        for line in range(5):
            yy = -.145 + line*.052
            end = .88 if line % 2 else .75
            points = [surface(u, side, yy, .003) for u in (.16, .35, .54, end)]
            if line != 2 or side == -1:
                _cls_prop_tube(name + '_ink_line', points, .0023, M['ink'], coll, book)
        if side == 1:
            pts = [surface(.52+.20*math.cos(t), side, .018+.044*math.sin(t), .005)
                   for t in [i*math.tau/24 for i in range(24)]]
            _cls_prop_tube(name + '_page_sigil', pts, .003, M['brass'], coll, book, True)
            pts = [surface(u, side, y, .006) for u, y in
                   ((.52, .076), (.75, -.025), (.29, -.025), (.52, .076))]
            _cls_prop_tube(name + '_page_triangle', pts, .0025, M['ink'], coll, book)
    _cls_prop_tube(name + '_ribbon', [(0, -.15, .057), (.01, -.245, .04),
                                    (.023, -.285, .015), (.042, -.31, .009)],
                   .007, M['book_red'], coll, book)
    return book


def _cls_bottle(name, pos, size, color, M, coll, root=None, shared=None):
    bottle = empty(name + '_root', pos, coll)
    if root:
        _cls_prop_parent(bottle, root)
    bottle.scale = (size, size, size)
    # 液体外观采用玻璃壳 + 明亮核心，避免把装饰瓶变成不可读透明球。
    pieces = []
    pieces.append(_cls_prop_sphere(name + '_glass', (0, 0, .105), (.09, .09, .105),
                                   M['glass'], coll, bottle, 16, 8))
    pieces.append(_cls_prop_sphere(name + '_elixir', (0, 0, .086), (.073, .073, .072),
                                   M[color], coll, bottle, 16, 8))
    pieces.append(_cls_prop_cyl(name + '_neck', (0, 0, .212), .039, .086,
                                M['glass'], coll, bottle, vertices=16))
    pieces.append(_cls_prop_cyl(name + '_lip', (0, 0, .248), .049, .023,
                                M['brass'], coll, bottle, vertices=16))
    pieces.append(_cls_prop_cyl(name + '_cork', (0, 0, .268), .034, .037,
                                M['wood_light'], coll, bottle, vertices=12))
    pieces.append(_cls_prop_box(name + '_label', (0, -.086, .113), (.068, .008, .045),
                                M['paper'], coll, bottle, .008))
    pieces.append(_cls_prop_box(name + '_seal', (0, -.093, .113), (.018, .008, .024),
                                M['brass'], coll, bottle, .004))
    # 同色、同形瓶的部件共享几何，变体靠父级缩放产生。
    if shared is not None:
        key = color
        if key in shared:
            for ob, source in zip(pieces, shared[key]):
                old = ob.data
                ob.data = source.data
                if old.users == 0:
                    bpy.data.meshes.remove(old)
        else:
            shared[key] = pieces
    return bottle


def _cls_quill(name, pos, angle, M, coll, root):
    quill = empty(name + '_root', pos, coll)
    _cls_prop_parent(quill, root)
    quill.rotation_euler.z = angle
    _cls_prop_cyl(name + '_inkwell', (0, 0, .037), .058, .074, M['ink'], coll, quill)
    _cls_prop_cyl(name + '_rim', (0, 0, .08), .039, .014, M['brass'], coll, quill)
    points = [(0, 0, .075), (.025, .006, .17), (.085, .02, .30), (.16, .026, .44)]
    _cls_prop_tube(name + '_shaft', points, .005, M['brass'], coll, quill)
    verts = [(.025,.009,.17), (.014,.009,.26), (.025,.012,.34),
             (.080,.020,.41), (.16,.026,.44), (.127,.025,.34),
             (.107,.023,.25), (.065,.015,.18), (.085,.020,.30)]
    faces = [(8, i, (i+1) % 8) for i in range(8)]
    feather = mesh_obj(name + '_feather', verts, faces, M['paper'], coll)
    _cls_prop_parent(feather, quill)
    for i in range(4):
        z = .24+i*.035
        x = .055+i*.024
        _cls_prop_tube(name + '_barb', [(x-.035, .018, z+.025), (x, .021, z),
                                      (x+.027, .023, z-.025)],
                       .0018, M['wood_light'], coll, quill)


def _cls_crystal_triad(name, pos, M, coll, root):
    stand = empty(name + '_root', pos, coll)
    _cls_prop_parent(stand, root)
    _cls_prop_box(name + '_tray', (0, 0, .013), (.36, .17, .026), M['wood_dark'],
                  coll, stand, .03)
    for index, (x, r, mat) in enumerate(((-.112,.049,'magic_lilac'),
                                       (0,.060,'magic_blue'), (.112,.043,'star'))):
        _cls_prop_cyl(name + '_cup_' + str(index), (x, 0, .037), r*.78, .022,
                      M['brass'], coll, stand, vertices=16)
        _cls_prop_sphere(name + '_orb_' + str(index), (x, 0, .07+r*.4), (r,r,r),
                         M['glass'], coll, stand, 16, 8)
        _cls_prop_sphere(name + '_heart_' + str(index), (x, 0, .07+r*.4),
                         (r*.52,r*.52,r*.52), M[mat], coll, stand, 12, 6)


def _cls_student_desk(index, x, y, M, coll):
    root = empty('desk_%02d_root' % index, (x, y, 0), coll)
    for j in range(3):
        _cls_prop_box('desk_%02d_top_plank_%d' % (index,j), (0, (j-1)*.232, .735),
                      (1.9, .224, .09), M['wood_light'], coll, root, .045)
    for xx in (-.73, .73):
        for yy in (-.235,.235):
            _cls_prop_box('desk_%02d_leg' % index, (xx, yy, .355), (.085,.095,.70),
                          M['wood'], coll, root, .015, (0, -.035 if xx<0 else .035, 0))
            _cls_prop_cyl('desk_%02d_joinery_peg' % index, (xx, yy-.052, .61), .022,
                          .016, M['wood_dark'], coll, root, 12, (math.pi/2,0,0))
        _cls_prop_box('desk_%02d_end_stretcher' % index, (xx, 0, .20), (.075,.57,.07),
                      M['wood'], coll, root, .012)
    _cls_prop_box('desk_%02d_long_stretcher' % index, (0, .05, .24), (1.52,.07,.07),
                  M['wood_dark'], coll, root, .012)
    _cls_prop_box('desk_%02d_apron' % index, (0, -.285, .63), (1.62,.055,.11),
                  M['wood'], coll, root, .012)
    # 长凳的圆端、榫头与横撑在近景仍有结构。
    _cls_prop_box('bench_%02d_seat' % index, (0,-.75,.405), (1.48,.33,.09),
                  M['wood_light'], coll, root, .035)
    for xx in (-.74,.74):
        _cls_prop_cyl('bench_%02d_round_end' % index, (xx,-.75,.405), .165,.09,
                      M['wood_light'], coll, root, 24)
    for xx in (-.58,.58):
        for yy in (-.855,-.645):
            _cls_prop_box('bench_%02d_leg' % index, (xx,yy,.19), (.075,.075,.38),
                          M['wood'], coll, root, .012)
    _cls_prop_box('bench_%02d_stretcher' % index, (0,-.75,.14), (1.25,.065,.065),
                  M['wood_dark'], coll, root, .01)
    for xx in (-.61,.61):
        _cls_prop_box('bench_%02d_crosspiece' % index, (xx,-.75,.24), (.085,.35,.065),
                      M['wood'], coll, root, .012)
    _cls_open_book('desk_%02d_book' % index, (-.27,-.03,.785), .94,
                   (-.085,.04,.09,-.055,.03,-.12)[index], M, coll,
                   ('book_red','book_green','book_blue')[index % 3], root)
    _cls_quill('desk_%02d_quill' % index, (-.76,.12,.785), -.25+index*.13, M, coll, root)
    _cls_bottle('desk_%02d_potion' % index, (.67,.12,.785), .84+index*.025,
                ('liquid_a','liquid_b','liquid_c')[index % 3], M, coll, root)
    _cls_crystal_triad('desk_%02d_crystals' % index, (.41,-.14,.785), M, coll, root)
    return root


def _cls_bookcase(M, coll):
    root = empty('library_low_bookcase_root', (4.10,.48,0), coll)
    length = 4.95
    # 随右墙作剖切：省略背板，让主相机能看到藏书而不是封闭柜背。
    for yy in (-length/2, -length/6, length/6, length/2):
        _cls_prop_box('library_divider', (0,yy,1.10), (.62,.075,2.20),
                      M['wood'], coll, root, .025)
    for height in (.13,.635,1.14,1.645,2.16):
        _cls_prop_box('library_shelf', (-.005,0,height), (.65,length+.10,.075),
                      M['wood_light'], coll, root, .022)
        _cls_prop_box('library_shelf_moulding', (-.335,0,height-.015), (.035,length+.10,.09),
                      M['wood'], coll, root, .012)
    _cls_prop_box('library_crown', (0,0,2.215), (.70,length+.20,.09),
                  M['wood'], coll, root, .035)
    rng = random.Random(321)
    sources = [_cls_book_source('library_book_master_%d' % i, M[key], M, coll)
               for i,key in enumerate(('book_red','book_blue','book_green','wood_dark','purple'))]
    for row in range(4):
        for bay in range(3):
            for index in range(10):
                yy = -2.35 + bay*1.65 + index*.145
                src = sources[(index+row*2+bay) % len(sources)]
                _cls_book_instance(src, 'library_book_%d_%d_%02d' % (row,bay,index), coll,
                                   root, (-.02+rng.uniform(-.025,.025), yy,
                                          .17+row*.505),
                                   (rng.uniform(.77,.97), rng.uniform(1.02,1.30),
                                    rng.uniform(.81,1.03)), rz=math.pi/2,
                                   lean=rng.uniform(-.035,.035))
    for source in sources:
        bpy.data.objects.remove(source, do_unlink=True)
    return root


def _cls_elixir_cabinet(M, coll):
    root = empty('elixir_cabinet_root', (-3.70,4.20,.18), coll)
    _cls_prop_box('cabinet_back', (0,.25,1.14), (1.20,.075,2.26), M['wood_dark'], coll, root)
    for xx in (-.59,.59):
        _cls_prop_box('cabinet_carved_side', (xx,0,1.17), (.09,.59,2.32),
                      M['wood'], coll, root, .035)
        _cls_prop_box('cabinet_front_pilaster', (xx,-.31,1.15), (.105,.07,2.19),
                      M['wood_light'], coll, root, .018)
    for zz in (.12,.65,1.18,1.71,2.28):
        _cls_prop_box('cabinet_shelf', (0,-.015,zz), (1.22,.63,.075), M['wood'], coll, root)
        _cls_prop_box('cabinet_brass_edge', (0,-.34,zz), (1.18,.014,.023),
                      M['brass'], coll, root, .004)
    _cls_prop_box('cabinet_cornice', (0,0,2.36), (1.34,.72,.12),
                  M['wood_light'], coll, root, .035)
    shared = {}
    for row in range(4):
        for column in range(6):
            color = ('liquid_a','liquid_b','liquid_c')[(row+column)%3]
            _cls_bottle('cabinet_bottle_%d_%d' % (row,column),
                        (-.46+column*.184, -.05, .162+row*.53),
                        1.0+((column+row)%3)*.13, color, M, coll, root, shared)
    # 橱顶中心徽章与两侧小圆饰件。
    _cls_prop_cyl('cabinet_crest', (0,-.365,2.40), .105,.018, M['brass'],
                  coll, root, 32, (math.pi/2,0,0))
    _cls_prop_sphere('cabinet_crest_gem', (0,-.383,2.40), (.043,.018,.043),
                     M['magic_blue'], coll, root)
    return root


def _cls_teachers_desk(M, coll):
    root = empty('teachers_desk_root', (-.60,3.90,.18), coll)
    for i in range(4):
        _cls_prop_box('teacher_desktop_plank', (0,(i-1.5)*.20,.955), (2.0,.194,.09),
                      M['wood_light'], coll, root, .035)
    for xx in (-.79,.79):
        for yy in (-.25,.25):
            _cls_prop_box('teacher_desk_leg', (xx,yy,.455), (.13,.14,.91),
                          M['wood'], coll, root, .023)
            _cls_prop_cyl('teacher_leg_brass_foot', (xx,yy,.10), .078,.10,
                          M['brass'], coll, root, 16)
    _cls_prop_box('teacher_desk_front', (0,-.29,.70), (1.72,.10,.37), M['wood'], coll, root)
    for xx in (-.48,.48):
        _cls_prop_box('teacher_desk_drawer', (xx,-.355,.72), (.77,.045,.22),
                      M['wood_light'], coll, root, .025)
        _cls_prop_cyl('teacher_desk_pull', (xx,-.39,.72), .026,.04, M['brass'],
                      coll, root, 16, (math.pi/2,0,0))
    _cls_prop_box('teacher_desk_stretcher', (0,.18,.23), (1.70,.10,.10), M['wood_dark'], coll, root)
    _cls_open_book('teacher_grimoire', (-.13,-.03,1.005), 1.28, -.055, M, coll, 'book_blue', root)
    _cls_quill('teacher_quill', (-.78,.12,1.005), -.4, M, coll, root)
    _cls_bottle('teacher_ink_elixir', (.76,.08,1.005), 1.22, 'liquid_b', M, coll, root)
    _cls_prop_box('teacher_notes', (.58,-.13,1.01), (.28,.29,.014), M['paper'], coll, root, .008,
                  (0,0,.17))
    return root


def _cls_globe(M, coll):
    root = empty('terrestrial_globe_root', (1.25,4.50,.18), coll)
    _cls_prop_cyl('globe_base', (0,0,.06), .31,.12, M['wood_dark'], coll, root, 32)
    _cls_prop_cyl('globe_base_band', (0,0,.13), .25,.035, M['brass'], coll, root, 32)
    _cls_prop_cyl('globe_pedestal', (0,0,.48), .065,.70, M['wood'], coll, root)
    _cls_prop_sphere('globe_pedestal_knot', (0,0,.67), (.10,.10,.14), M['wood_light'], coll, root)
    globe = empty('globe_sphere_root', (0,0,1.12), coll)
    _cls_prop_parent(globe, root)
    globe.rotation_euler = (.12,.24,0)
    _cls_prop_sphere('globe_blue_world', (0,0,0), (.36,.36,.36), M['blue'], coll, globe, 32,16)
    for j in (-1,0,1):
        h = j*.16
        r = math.sqrt(.362**2-h*h)
        pts = [(r*math.cos(i*math.tau/64),r*math.sin(i*math.tau/64),h) for i in range(64)]
        _cls_prop_tube('globe_latitude', pts,.0035,M['brass'],coll,globe,True)
    for angle in (0,math.pi/3,2*math.pi/3):
        pts = [(math.cos(angle)*.362*math.cos(i*math.tau/64),
                math.sin(angle)*.362*math.cos(i*math.tau/64),
                .362*math.sin(i*math.tau/64)) for i in range(64)]
        _cls_prop_tube('globe_longitude', pts,.0035,M['brass'],coll,globe,True)
    # 抽象陆地沿球面铺展，使用厚度极小的曲面片。
    for n,(lon,lat) in enumerate(((-1.8,.3),(-.6,-.45),(.7,.5),(2.5,-.3))):
        verts = []
        for i in range(15):
            theta = i*math.tau/14
            a = lon + .37*math.cos(theta)*(1+.2*math.sin(theta*3+n))
            b = lat + .32*math.sin(theta)*(1+.2*math.cos(theta*4))
            verts.append((.365*math.cos(b)*math.cos(a), .365*math.cos(b)*math.sin(a), .365*math.sin(b)))
        verts.append((.365*math.cos(lat)*math.cos(lon),.365*math.cos(lat)*math.sin(lon),.365*math.sin(lat)))
        ob=mesh_obj('globe_land_%d'%n,verts,[(15,i,(i+1)%14) for i in range(14)],M['leaf2'],coll)
        _cls_prop_parent(ob,globe)
    pts=[(.45*math.cos(i*math.tau/72),0,.45*math.sin(i*math.tau/72)) for i in range(72)]
    _cls_prop_tube('globe_meridian_cradle',pts,.018,M['brass'],coll,globe,True)
    return root


def _cls_magic_plant(M, coll):
    root=empty('moonfern_root',(-3.3,-4.4,0),coll)
    _cls_prop_cyl('moonfern_pot',(0,0,.21),.32,.42,M['pot'],coll,root,32,radius2=.25)
    _cls_prop_cyl('moonfern_pot_rim',(0,0,.42),.34,.075,M['pot'],coll,root,32)
    _cls_prop_cyl('moonfern_soil',(0,0,.447),.295,.025,M['wood_dark'],coll,root,32)
    for n in range(11):
        angle=n*2.39996
        height=.72+(n%3)*.12
        outward=.32+(n%2)*.12
        end=Vector((math.cos(angle)*outward,math.sin(angle)*outward,height))
        start=Vector((0,0,.44))
        mid=start.lerp(end,.55)+Vector((0,0,.12))
        _cls_prop_tube('moonfern_stem',[start,mid,end],.009,M['leaf'],coll,root)
        # 舟形叶片中央拱起，叶脉与发光尖端提供可读轮廓。
        tangent=Vector((-math.sin(angle),math.cos(angle),0))
        tip=end+Vector((math.cos(angle)*.15,math.sin(angle)*.15,.09))
        base=mid.lerp(end,.25)
        center=base.lerp(tip,.55)+Vector((0,0,.055))
        verts=[tuple(base),tuple(center+tangent*.105),tuple(tip),tuple(center-tangent*.105),tuple(center)]
        ob=mesh_obj('moonfern_leaf_%d'%n,verts,[(0,1,4),(1,2,4),(2,3,4),(3,0,4)],
                    M['leaf2' if n%2 else 'leaf'],coll)
        _cls_prop_parent(ob,root)
        _cls_prop_tube('moonfern_vein',[base,center,tip],.004,M['plant_glow'],coll,root)
        if n%3==0:
            _cls_prop_sphere('moonfern_luminous_seed',tuple(tip),(.028,.028,.043),
                             M['plant_glow'],coll,root,12,6)
    return root


def build_furniture(M, C):
    """六套桌凳；最后一排右桌及其所有小物归入 FG。"""
    roots=[]
    for row,y in enumerate((1.70,-.50,-2.70)):
        for col,x in enumerate((-1.60,1.60)):
            coll=C['fg'] if row==2 and col==1 else C['furniture']
            roots.append(_cls_student_desk(row*2+col,x,y,M,coll))
    roots.append(_cls_bookcase(M,C['furniture']))
    roots.append(_cls_elixir_cabinet(M,C['furniture']))
    roots.append(_cls_teachers_desk(M,C['furniture']))
    roots.append(_cls_globe(M,C['furniture']))
    roots.append(_cls_magic_plant(M,C['furniture']))
    return roots


def _cls_candle(name, pos, height, phase, M, coll, floating=False):
    root=empty(name+'_root',pos,coll)
    _cls_prop_cyl(name+'_saucer',(0,0,.015),.105,.027,M['brass'],coll,root,24)
    _cls_prop_cyl(name+'_saucer_foot',(0,0,-.013),.046,.037,M['metal'],coll,root,16)
    _cls_prop_cyl(name+'_wax',(0,0,height*.5+.032),.052,height,M['paper'],coll,root,20)
    for n in range(4):
        angle=n*1.7+phase
        z=height+.025-(n%3)*.025
        _cls_prop_sphere(name+'_wax_drip',(math.cos(angle)*.047,math.sin(angle)*.047,z),
                         (.015,.015,.045+(n%2)*.022),M['paper'],coll,root,12,6)
    _cls_prop_cyl(name+'_wick',(0,0,height+.055),.006,.036,M['ink'],coll,root,8)
    flame=_cls_prop_sphere(name+'_flame',(0,0,height+.128),(.032,.032,.084),
                            M['flame'],coll,root,16,8)
    register_flame(flame,phase=phase)
    core=_cls_prop_sphere(name+'_flame_heart',(0,0,height+.106),(.015,.015,.042),
                           M['star'],coll,root,12,6)
    register_flame(core,phase=phase+.15)
    if floating:
        register_float(root,amp=.065+height*.08,phase=phase,spin=.08)
    return root


def _cls_orrery(M,coll):
    root=empty('orrery_root',(0,-3.20,3.90),coll)
    # 球形日心、三条倾斜轨道、七颗具有不同尺度的行星。
    _cls_prop_sphere('orrery_sun',(0,0,0),(.15,.15,.15),M['star'],coll,root,24,12)
    _cls_prop_cyl('orrery_axis',(0,0,.09),.017,.65,M['brass'],coll,root,16)
    _cls_prop_sphere('orrery_axis_finial',(0,0,.43),(.042,.042,.075),M['brass'],coll,root)
    radii=(.48,.73,1.02)
    angles=((.18,.16,0),(-.3,.18,.2),(.21,-.2,-.15))
    matrices=[Euler(a,'XYZ').to_matrix() for a in angles]
    for n,radius in enumerate(radii):
        points=[tuple(matrices[n]@Vector((radius*math.cos(i*math.tau/96),
                                         radius*math.sin(i*math.tau/96),0))) for i in range(96)]
        _cls_prop_tube('orrery_orbit_%d'%n,points,.011,M['brass'],coll,root,True)
    mats=('magic_blue','purple','leaf2','book_red','blue','wood_light','magic_lilac')
    for n in range(7):
        orbit=0 if n<2 else 1 if n<4 else 2
        angle=n*2.39996+.35
        pos=matrices[orbit]@Vector((radii[orbit]*math.cos(angle),radii[orbit]*math.sin(angle),0))
        radius=(.045,.056,.066,.052,.091,.072,.047)[n]
        _cls_prop_sphere('orrery_planet_%d'%n,tuple(pos),(radius,)*3,M[mats[n]],coll,root,20,10)
        if n in (4,5):
            points=[tuple(pos+matrices[orbit]@Vector((radius*1.8*math.cos(i*math.tau/40),
                                                    radius*1.8*math.sin(i*math.tau/40),0))) for i in range(40)]
            _cls_prop_tube('orrery_planet_ring_%d'%n,points,.006,M['brass'],coll,root,True)
    # 三条短悬索收束于顶端吊环，不跨过投影保护区域。
    for angle in (0,math.tau/3,math.tau*2/3):
        _cls_prop_tube('orrery_suspension',[(.56*math.cos(angle),.56*math.sin(angle),.13),
                                         (.14*math.cos(angle),.14*math.sin(angle),.57),
                                         (0,0,.67)],.006,M['metal'],coll,root)
    points=[(.066*math.cos(i*math.tau/32),0,.70+.066*math.sin(i*math.tau/32)) for i in range(32)]
    _cls_prop_tube('orrery_hanging_loop',points,.010,M['brass'],coll,root,True)
    register_float(root,amp=.03,phase=.3,spin=math.tau)
    return root


def build_magic_props(M,C):
    coll=C['magic']
    roots=[]
    placements=[(-1.78,-2.1,2.85,.76,-.34,.17),
                (.32,-1.40,2.72,.83,.22,-.13),
                (1.75,-2.52,3.18,.72,-.2,.13),
                (-.78,-3.38,3.16,.78,.44,-.18)]
    for n,(x,y,z,size,rz,rx) in enumerate(placements):
        root=_cls_open_book('floating_grimoire_%d'%n,(x,y,z),size,rz,M,coll,
                             ('book_red','book_blue','book_green','purple')[n])
        root.rotation_euler.x=rx
        root.rotation_euler.y=(-.14,.17,-.1,.12)[n]
        register_float(root,amp=.075+n*.012,phase=n*1.43,spin=.14*(-1 if n%2 else 1))
        roots.append(root)
    candle_positions=[(-1.90,-1.10,3.06),(-1.05,-1.12,3.48),(.02,-.92,3.34),
                      (1.10,-1.13,3.46),(1.90,-1.43,2.85),(-1.61,-2.90,3.53),
                      (-.53,-2.50,2.89),(.72,-2.71,2.82),(1.60,-3.40,3.55),
                      (-1.70,-3.42,2.93)]
    for n,pos in enumerate(candle_positions):
        roots.append(_cls_candle('floating_candle_%02d'%n,pos,.16+(n%3)*.045,
                                  n*.71,M,coll,True))
    roots.append(_cls_orrery(M,coll))
    # 六支固定蜡烛位于讲桌与低书架，顶部火焰仍参加循环动画。
    for n,pos in enumerate(((-1.45,3.58,1.18),(.17,3.58,1.18),
                            (4.04,-1.90,2.265),(4.04,-1.50,2.265),
                            (4.04,-1.10,2.265),(4.04,-.70,2.265))):
        _cls_candle('stationary_candle_%02d'%n,pos,.17+(n%3)*.055,n*.87,
                     M,C['furniture'],False)
    return roots
