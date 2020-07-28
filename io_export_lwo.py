#
# +---------------------------------------------------------+
# | Copyright (c) 2002 Anthony D'Agostino                   |
# | http://www.redrival.com/scorpius                        |
# | scorpius@netzero.com                                    |
# | April 21, 2002                                          |
# | Read and write LightWave Object File Format (*.lwo)     |
# +---------------------------------------------------------+

# ***** BEGIN GPL LICENSE BLOCK *****
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
# ***** END GPL LICENCE BLOCK *****


"""\
This script exports self.meshes to LightWave file format.

LightWave is a full-featured commercial modeling and rendering
application. The lwo file format is composed of 'chunks,' is well
defined, and easy to read and write. It is similar in structure to the
trueSpace cob format.

Usage:<br>
    Select self.meshes to be exported and run this script from "File->Export" menu.

Supported:<br>
    UV Coordinates, Meshes, Materials, Material Indices, Specular
Highlights, and Vertex Colors. For added functionality, each object is
placed on its own layer. Someone added the CLIP chunk and imagename support.

Missing:<br>
    Not too much, I hope! :).

Known issues:<br>
    Empty objects crash has been fixed.

Notes:<br>
    For compatibility reasons, it also reads lwo files in the old LW
v5.5 format.
"""

bl_info = {
    "name": "Lightwave Object (LWO) format",
    "author": "Anthony D'Agostino (Scorpius), Gert De Roost, The Dark Mod team",
    "version": (2, 8, 0),
    "blender": (2, 80, 0),
    "location": "File > Export",
    "description": "Export to Lightwave LWO format",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export"}

import bpy, bmesh
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty
from bpy.app.handlers import persistent
import os, math
try: import struct
except: struct = None
try: import io
except: io = None
try: import operator
except: operator = None

bpy.types.Material.vcmenu = EnumProperty(
            items = [("<none>", "<none>", "<none>")],
            name = "Vertex Color Map",
            description = "LWO export: vertex color map for this material",
            default = "<none>")

class idTechVertexColors(bpy.types.Panel):
    bl_label = "LwoExport Vertex Color Map"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    @classmethod
    def poll(self, context):
        return context.active_object.active_material!=None

    def draw(self, context):
        layout = self.layout
        layout.prop(context.active_object.active_material, 'vcmenu')

class MessageOperator(bpy.types.Operator):
    bl_idname = "lwoexport.message"
    bl_label = "Saved"

    def invoke(self, context, event):

        wm = context.window_manager
        return wm.invoke_popup(self, width=500, height=20)

    def draw(self, context):

        layout = self.layout
        row = layout.row()
        row.label(text = '', icon = "ERROR")
        row.label(text="Error | This exporter requires a full python installation")

# LWO export helper functions
# -----------------------------------------------------------------------------

def generate_nstring(string):
    "Generate a null terminated string with an even number of bytes"
    if len(string) % 2 == 0:  # even
        string += "\0\0"
    else:                   # odd
        string += "\0"
    return string

def write_chunk(dest_file, name, data):
    "Write a named LWO chunk to the given file-like object"
    dest_file.write(bytes(name, 'UTF-8'))
    dest_file.write(struct.pack(">L", len(data)))
    dest_file.write(data)

def write_header(dest_file, chunks):
    "Write an LWO header including the size of contained chunks"
    total_chunk_size = sum([len(chunk) for chunk in chunks])
    form_size = total_chunk_size + len(chunks)*8 + len("FORM")
    dest_file.write(b"FORM")
    dest_file.write(struct.pack(">L", form_size))
    dest_file.write(b"LWO2")

def generate_vx(index):
    """Generate and return an LWO-formatted index

    The index is packed either as 16 bits or 32 bits depending on its numerical
    value."""

    if index < 0xFF00:
        return struct.pack(">H", index)                 # 2-byte index
    else:
        return struct.pack(">L", index | 0xFF000000)    # 4-byte index

def generate_vertex_colors(mesh):
    "Generate and return vertex color block"

    alldata = []

    # For each vertex color layer
    for layer in mesh.vertex_colors:

        # Construct output stream for this layer
        data = io.BytesIO()
        data.write(b"RGBA")                                      # type
        data.write(struct.pack(">H", 4))                         # dimension
        data.write(bytes(generate_nstring(layer.name), 'UTF-8')) # name

        found = False
        for face_idx, face in enumerate(mesh.polygons):
            for vert_idx, loop in zip(face.vertices, face.loop_indices):
                (r, g, b, a) = layer.data[loop].color
                data.write(generate_vx(vert_idx))
                data.write(generate_vx(face_idx))
                data.write(struct.pack(">ffff", r, g, b, a))
                found = True
        if found:
            alldata.append(data.getvalue())

    return alldata

def generate_mesh_surface(mesh, material_name):
    "Generate and return mesh surface block"

    data = io.BytesIO()
    data.write(bytes(generate_nstring(material_name), 'UTF-8'))

    try:
        material = bpy.data.materials.get(material_name)
        R,G,B = material.diffuse_color[0], material.diffuse_color[1], material.diffuse_color[2]
        diff = material.diffuse_intensity
        lumi = material.emit
        spec = material.specular_intensity
        gloss = math.sqrt((material.specular_hardness - 4) / 400)
        if material.raytrace_mirror.use:
            refl = material.raytrace_mirror.reflect_factor
        else:
            refl = 0.0
        rblr = 1.0 - material.raytrace_mirror.gloss_factor
        rind = material.raytrace_transparency.ior
        tran = 1.0 - material.alpha
        tblr = 1.0 - material.raytrace_transparency.gloss_factor
        trnl = material.translucency
        if mesh.use_auto_smooth:
            sman = mesh.auto_smooth_angle
        else:
            sman = 0.0
    except:
        material = None

        R=G=B = 1.0
        diff = 1.0
        lumi = 0.0
        spec = 0.2
        hard = 0.0
        gloss = 0.0
        refl = 0.0
        rblr = 0.0
        rind = 1.0
        tran = 0.0
        tblr = 0.0
        trnl = 0.0
        sman = 0.0

    data.write(b"COLR")
    data.write(struct.pack(">H", 0))

    data.write(b"COLR")
    data.write(struct.pack(">H", 14))
    data.write(struct.pack(">fffH", R, G, B, 0))

    data.write(b"DIFF")
    data.write(struct.pack(">H", 6))
    data.write(struct.pack(">fH", diff, 0))

    data.write(b"LUMI")
    data.write(struct.pack(">H", 6))
    data.write(struct.pack(">fH", lumi, 0))

    data.write(b"SPEC")
    data.write(struct.pack(">H", 6))
    data.write(struct.pack(">fH", spec, 0))

    data.write(b"GLOS")
    data.write(struct.pack(">H", 6))
    data.write(struct.pack(">fH", gloss, 0))

    if material:
        vcname = material.vcmenu
        if vcname != "<none>":
            data.write(b"VCOL")
            data_tmp = io.BytesIO()
            data_tmp.write(struct.pack(">fH4s", 1.0, 0, b"RGBA"))  # intensity, envelope, type
            data_tmp.write(bytes(generate_nstring(vcname), 'UTF-8')) # name
            data.write(struct.pack(">H", len(data_tmp.getvalue())))
            data.write(data_tmp.getvalue())

    data.write(b"SMAN")
    data.write(struct.pack(">H", 4))
    data.write(struct.pack(">f", sman))

    return data.getvalue()

DEFAULT_NAME = "Blender Default"

def generate_default_surf(self):
    "Generate a default mesh surface block"

    data = io.BytesIO()
    material_name = DEFAULT_NAME
    data.write(bytes(generate_nstring(material_name), 'UTF-8'))

    data.write(b"COLR")
    data.write(struct.pack(">H", 14))
    data.write(struct.pack(">fffH", 0.9, 0.9, 0.9, 0))

    data.write(b"DIFF")
    data.write(struct.pack(">H", 6))
    data.write(struct.pack(">fH", 0.8, 0))

    data.write(b"LUMI")
    data.write(struct.pack(">H", 6))
    data.write(struct.pack(">fH", 0, 0))

    data.write(b"SPEC")
    data.write(struct.pack(">H", 6))
    data.write(struct.pack(">fH", 0.4, 0))

    data.write(b"GLOS")
    data.write(struct.pack(">H", 6))
    gloss = 50 / (255/2.0)
    gloss = round(gloss, 1)
    data.write(struct.pack(">fH", gloss, 0))

    return data.getvalue()

# Main export class
# -----------------------------------------------------------------------------

class LwoExport(bpy.types.Operator, ExportHelper):
    "Main exporter class"

    bl_idname = "export.lwo"
    bl_label = "LwoExport"
    bl_description = "Export Lightwave .lwo file"
    bl_options = {"REGISTER"}
    filename_ext = ".lwo"
    filter_glob: StringProperty(default = "*.lwo", options = {'HIDDEN'})

    filepath: StringProperty(
        name = "File Path",
        description = "File path used for exporting the .lwo file",
        maxlen = 1024,
        default = "" )

    option_smooth: EnumProperty(
            name = "Smooth",
            description = "How to smooth exported mesh data",
            items = [
                ('NONE', 'None', 'No smoothing'),
                ('FULL', 'Full', 'Entire object is smoothed'),
                ('FROM_OBJECT', 'As rendered',
                 'Export smoothing status and autosmooth angles from Blender object')
            ],
            default = 'FROM_OBJECT' )

    option_subd: BoolProperty(
            name = "Export as subpatched",
            description = "Export mesh data as subpatched",
            default = False )

    option_applymod: BoolProperty(
            name = "Apply modifiers",
            description = "Applies modifiers before exporting",
            default = True )

    option_triangulate: BoolProperty(
            name = "Triangulate",
            description = "Triangulates all exportable objects",
            default = True )

    option_normals: BoolProperty(
            name = "Recalculate Normals",
            description = "Recalculate normals before exporting",
            default = False )

    option_remove_doubles: BoolProperty(
            name = "Remove Doubles",
            description = "Remove any duplicate vertices before exporting",
            default = False )

    option_apply_scale: BoolProperty(
            name = "Scale",
            description = "Apply scale transformation",
            default = True )

    option_apply_location: BoolProperty(
            name = "Location",
            description = "Apply location transformation",
            default = True )

    option_apply_rotation: BoolProperty(
            name = "Rotation",
            description = "Apply rotation transformation",
            default = True )

    option_batch: BoolProperty(
            name = "Batch Export",
            description = "A separate .lwo file for every selected object",
            default = False )

    option_scale: FloatProperty(
            name = "Scale",
            description = "Object scaling factor (default: 1.0)",
            min = 0.01,
            max = 1000.0,
            soft_min = 0.01,
            soft_max = 1000.0,
            default = 1.0 )

    def draw( self, context ):
        layout = self.layout

        box = layout.box()

        box.prop( self, 'option_applymod' )
        box.prop( self, 'option_subd' )
        box.prop( self, 'option_triangulate' )
        box.prop( self, 'option_normals' )
        box.prop( self, 'option_remove_doubles' )
        box.prop( self, 'option_smooth' )

        box.separator()
        box.label( text="Transformations:" )
        box.prop( self, 'option_apply_scale' )
        box.prop( self, 'option_apply_rotation' )
        box.prop( self, 'option_apply_location' )

        box.label( text="Advanced:" )
        box.prop( self, 'option_scale' )
        box.prop( self, 'option_batch')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.type == 'MESH')

    def execute(self, context):

        global main

        main = self

        self.context = context
        self.VCOL_NAME = "Per-Face Vertex Colors"

        if struct and io and operator:
            self.write(self.filepath)
        else:
            bpy.ops.lwoexport.message('INVOKE_DEFAULT')


        return {'FINISHED'}

    # ==============================
    # === Write LightWave Format ===
    # ==============================
    def write(self, filename):
        objects = list(self.context.selected_objects)
        actobj = self.context.active_object

        try:    objects.sort( key = lambda a: a.name )
        except: objects.sort(lambda a,b: cmp(a.name, b.name))

        self.meshes = []
        object_name_lookup_orig = {}
        mesh_object_name_lookup = {} # for name lookups only
        objdups = []

        # Certain operations only work on OBJECT mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Create duplicates of objects to export, so we can perform operations
        # like removing doubles without modifying the original objects
        for obj in objects:
            if obj.type != 'MESH':
                continue

            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = obj
            obj.select_set(state=True)
            bpy.ops.object.duplicate()
            objdup = bpy.context.active_object
            objdups.append(objdup)
            object_name_lookup_orig[objdup] = obj.name

            if self.option_applymod:
                if not(objdup.data.shape_keys):
                    while (len(objdup.modifiers)):
                        bpy.ops.object.modifier_apply(apply_as='DATA', modifier = objdup.modifiers[0].name)

            # Options
            bpy.ops.object.mode_set( mode = 'EDIT' )
            if self.option_remove_doubles:
                bpy.ops.object.mode_set( mode = 'EDIT' )
                bpy.ops.mesh.select_all( action = 'SELECT' )
                bpy.ops.mesh.remove_doubles()
            if self.option_triangulate:
                bpy.ops.mesh.select_all( action = 'SELECT' )
                bpy.ops.mesh.quads_convert_to_tris()
            if self.option_normals:
                bpy.ops.object.mode_set( mode = 'EDIT' )
                bpy.ops.mesh.select_all( action = 'SELECT' )
                bpy.ops.mesh.normals_make_consistent()

            # Transformations
            bpy.ops.object.mode_set( mode = 'OBJECT' )
            bpy.ops.object.transform_apply( location = self.option_apply_location, rotation = self.option_apply_rotation, scale = self.option_apply_scale )

            mesh = objdup.data
            if mesh:
                mesh_object_name_lookup[mesh] = obj.name
                if not(self.option_batch):
                    self.meshes.append(mesh)

        # Export each duplicated object
        for obj in objdups:
            if (self.option_batch):
                self.meshes = [obj.data]

            matmeshes, material_names = self.get_used_material_names()
            self.clips = []
            self.clippaths = []
            self.currclipid = 1
            tags = self.generate_tags(material_names)
            surfs = []
            chunks = [tags]

            meshdata = io.BytesIO()

            layer_index = 0

            # Generate LWO chunks
            for i, mesh in enumerate(self.meshes):
                if not(self.option_batch):
                    mobj = objdups[i]

                for j, m in enumerate(matmeshes):
                    if m == mesh:
                        surfs.append(self.generate_surface(m, material_names[j]))
                layr = self.generate_layr(mesh_object_name_lookup[mesh], layer_index)
                pnts = self.generate_pnts(mesh)
                bbox = self.generate_bbox(mesh)
                pols = self.generate_pols(mesh, self.option_subd)
                ptag = self.generate_ptag(mesh, material_names)

                if mesh.uv_layers:
                    vmad_uvs = self.generate_vmad_uv(mesh)  # per face

                write_chunk(meshdata, "LAYR", layr); chunks.append(layr)
                write_chunk(meshdata, "PNTS", pnts); chunks.append(pnts)
                write_chunk(meshdata, "BBOX", bbox); chunks.append(bbox)

                if mesh.vertex_colors:
                    vcs = generate_vertex_colors(mesh)  # per vert
                    for vmad in vcs:
                        write_chunk(meshdata, "VMAD", vmad)
                        chunks.append(vmad)
                write_chunk(meshdata, "POLS", pols); chunks.append(pols)
                write_chunk(meshdata, "PTAG", ptag); chunks.append(ptag)

                if mesh.uv_layers:
                    for vmad in vmad_uvs:
                        write_chunk(meshdata, "VMAD", vmad)
                        chunks.append(vmad)

                layer_index += 1

            for clip in self.clips:
                chunks.append(clip)
            for surf in surfs:
                chunks.append(surf)

            # Prepare the output file
            if (self.option_batch):
                filename = os.path.dirname(filename)
                filename += (os.sep + object_name_lookup_orig[obj].replace('.', '_'))
            if not filename.lower().endswith('.lwo'):
                filename += '.lwo'

            # Write generated chunk data to the output file
            with open(filename, "wb") as outfile:
                write_header(outfile, chunks)
                write_chunk(outfile, "TAGS", tags)
                outfile.write(meshdata.getvalue()); meshdata.close()
                for clip in self.clips:
                    write_chunk(outfile, "CLIP", clip)
                for surf in surfs:
                    write_chunk(outfile, "SURF", surf)

            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = obj
            obj.select_set(state=True)
            bpy.ops.object.delete()

            if not(self.option_batch):
                # if not batch exporting, all meshes of objects are already saved
                break

        for obj in objects:
            obj.select_set(state=True)
        bpy.context.view_layer.objects.active = actobj


    # ===============================
    # === Get Used Material Names ===
    # ===============================
    def get_used_material_names(self):
        matnames = []
        matmeshes = []
        for mesh in self.meshes:
            if mesh.materials:
                for material in mesh.materials:
                    if material:
                        matmeshes.append(mesh)
                        matnames.append(material.name)
            elif mesh.vertex_colors:
                matmeshes.append(mesh)
                matnames.append(self.LWO_VCOLOR_MATERIAL)
            else:
                matmeshes.append(mesh)
                matnames.append(self.LWO_DEFAULT_MATERIAL)
        return matmeshes, matnames

    # =========================================
    # === Generate Tag Strings (TAGS Chunk) ===
    # =========================================
    def generate_tags(self, material_names):
        data = io.BytesIO()
        if material_names:
            for mat in material_names:
                data.write(bytes(generate_nstring(mat), 'UTF-8'))
            return data.getvalue()
        else:
            return generate_nstring('')

    # ========================
    # === Generate Surface ===
    # ========================
    def generate_surface(self, mesh, name):
        if name == DEFAULT_NAME:
            return generate_default_surf()
        else:
            return generate_mesh_surface(mesh, name)

    # ===================================
    # === Generate Layer (LAYR Chunk) ===
    # ===================================
    def generate_layr(self, name, idx):
        px, py, pz = bpy.data.objects.get(name).location
        data = io.BytesIO()
        data.write(struct.pack(">h", idx))          # layer number
        data.write(struct.pack(">h", 0))            # flags
        data.write(struct.pack(">fff", px, pz, py)) # pivot
        data.write(bytes(generate_nstring(name.replace(" ","_").replace(".", "_")), 'UTF-8'))
        return data.getvalue()

    # ===================================
    # === Generate Verts (PNTS Chunk) ===
    # ===================================
    def generate_pnts(self, mesh):
        data = io.BytesIO()
        for i, v in enumerate(mesh.vertices):
            x, y, z = v.co
            x *= self.option_scale
            y *= self.option_scale
            z *= self.option_scale
            data.write(struct.pack(">fff", x, z, y))
        return data.getvalue()

    # ==========================================
    # === Generate Bounding Box (BBOX Chunk) ===
    # ==========================================
    def generate_bbox(self, mesh):
        data = io.BytesIO()
        # need to transform verts here
        if mesh.vertices:
            nv = [v.co for v in mesh.vertices]
            xx = [ co[0] * self.option_scale for co in nv ]
            yy = [ co[1] * self.option_scale for co in nv ]
            zz = [ co[2] * self.option_scale for co in nv ]
        else:
            xx = yy = zz = [0.0,]

        data.write(struct.pack(">6f", min(xx), min(zz), min(yy), max(xx), max(zz), max(yy)))
        return data.getvalue()

    # ================================================
    # === Generate Per-Face UV Coords (VMAD Chunk) ===
    # ================================================
    def generate_vmad_uv(self, mesh):
        alldata = []
        layers = mesh.uv_layers
        for l in layers:
            uvname = generate_nstring(l.name)
            data = io.BytesIO()
            data.write(b"TXUV")                                      # type
            data.write(struct.pack(">H", 2))                         # dimension
            data.write(bytes(uvname, 'UTF-8')) # name

            found = False
            for i, p in enumerate(mesh.polygons):
                for v, loop in zip(p.vertices, p.loop_indices):
                    searchl = list(p.loop_indices)
                    searchl.extend(list(p.loop_indices))
                    pos = searchl.index(loop)
                    prevl = searchl[pos - 1]
                    nextl = searchl[pos + 1]
                    youv = l.data[loop].uv
                    if l.data[prevl].uv == youv == l.data[nextl].uv:
                        continue
                    data.write(generate_vx(v)) # vertex index
                    data.write(generate_vx(i)) # face index
                    data.write(struct.pack(">ff", youv[0], youv[1]))
                    found = True
            if found:
                alldata.append(data.getvalue())

        return alldata

    # ===================================
    # === Generate Faces (POLS Chunk) ===
    # ===================================
    def generate_pols(self, mesh, subd):
        data = io.BytesIO()
        if subd:
            data.write(b"SUBD") # subpatch polygon type
        else:
            data.write(b"FACE") # normal polygon type
        for i,p in enumerate(mesh.polygons):
            data.write(struct.pack(">H", len(p.vertices))) # numfaceverts
            numfaceverts = len(p.vertices)
            p_vi = p.vertices
            for j in range(numfaceverts-1, -1, -1):         # Reverse order
                data.write(generate_vx(p_vi[j]))
        bm = bmesh.new()
        bm.from_mesh(mesh)
        for e in bm.edges:
            if len(e.link_faces) == 0:
                data.write(struct.pack(">H", 2))
                data.write(generate_vx(e.verts[0].index))
                data.write(generate_vx(e.verts[1].index))
        bm.to_mesh(mesh)

        return data.getvalue()

    # =================================================
    # === Generate Polygon Tag Mapping (PTAG Chunk) ===
    # =================================================
    def generate_ptag(self, mesh, material_names):
        data = io.BytesIO()
        data.write(b"SURF")
        for poly in mesh.polygons:
            if mesh.materials:
                matindex = poly.material_index
                matname = mesh.materials[matindex].name
                surfindex = material_names.index(matname)

                data.write(generate_vx(poly.index))
                data.write(struct.pack(">H", surfindex))
            else:
                data.write(generate_vx(poly.index))
                data.write(struct.pack(">H", 0))
        return data.getvalue()

def menu_func(self, context):
    self.layout.operator(LwoExport.bl_idname, text="Lightwave Object (.lwo)")

def register():
    bpy.app.handlers.depsgraph_update_post.append(sceneupdate_handler)

    bpy.utils.register_class(LwoExport)

    bpy.types.TOPBAR_MT_file_export.append(menu_func)

def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(sceneupdate_handler)

    bpy.utils.register_class(LwoExport)

    bpy.types.TOPBAR_MT_file_export.remove(menu_func)

if __name__ == "__main__":
  register()



@persistent
def sceneupdate_handler(dummy):

    ob = bpy.context.active_object
    if ob:
        if ob.type == 'MESH':
            mesh = bpy.context.active_object.data

            itemlist = [("<none>", "<none>", "<none>")]
            vcs = mesh.vertex_colors
            for vc in vcs:
                itemlist.append((vc.name, vc.name, "Vertex Color Map"))
            bpy.types.Material.vcmenu = EnumProperty(
                    items = itemlist,
                    name = "Vertex Color Map",
                    description = "LWO export: vertex color map for this material")

    return {'RUNNING_MODAL'}



