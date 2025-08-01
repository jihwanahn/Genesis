import os
import pickle as pkl

import numpy as np
import trimesh

import igl

import genesis as gs

from . import geom as gu
from . import mesh as mu


def box_to_elements(pos=(0, 0, 0), size=(1, 1, 1), tet_cfg=dict()):
    trimesh_obj = trimesh.creation.box(extents=size)
    trimesh_obj.vertices += np.array(pos)
    verts, elems = mu.tetrahedralize_mesh(trimesh_obj, tet_cfg)

    return verts, elems


def sphere_to_elements(pos=(0, 0, 0), radius=0.5, tet_cfg=dict()):
    trimesh_obj = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    trimesh_obj.vertices *= np.array(radius)
    trimesh_obj.vertices += np.array(pos)
    verts, elems = mu.tetrahedralize_mesh(trimesh_obj, tet_cfg)

    return verts, elems


def cylinder_to_elements():
    raise NotImplementedError


def mesh_to_elements(file, pos=(0, 0, 0), scale=1.0, tet_cfg=dict()):
    mesh = mu.load_mesh(file)
    mesh.vertices = mesh.vertices * scale

    # compute file name via hashing for caching
    tet_file_path = mu.get_tet_path(mesh.vertices, mesh.faces, tet_cfg)

    # loading pre-computed cache if available
    is_cached_loaded = False
    if os.path.exists(tet_file_path):
        gs.logger.debug("Tetrahedra file (`.tet`) found in cache.")
        try:
            with open(tet_file_path, "rb") as file:
                verts, elems = pkl.load(file)
            is_cached_loaded = True
        except (EOFError, ModuleNotFoundError, pkl.UnpicklingError):
            gs.logger.info("Ignoring corrupted cache.")

    if not is_cached_loaded:
        with gs.logger.timer(f"Tetrahedralization with configuration {tet_cfg} and generating `.tet` file:"):
            verts, elems = mu.tetrahedralize_mesh(mesh, tet_cfg)

            os.makedirs(os.path.dirname(tet_file_path), exist_ok=True)
            with open(tet_file_path, "wb") as file:
                pkl.dump((verts, elems), file)

    verts += np.array(pos)

    return verts, elems


def split_all_surface_tets(verts, elems):
    """
    Splits tetrahedras that have 4 vertices on the surface into 4 smaller tetrahedras.

    This is useful for the hydroelastic contact model.
    """
    F, *_ = igl.boundary_facets(elems)
    on_surface = np.zeros(verts.shape[0], dtype=bool)
    on_surface[
        F.reshape(
            -1,
        )
    ] = True
    all_on_surface = np.all(on_surface[elems], axis=1)
    if not all_on_surface.any():
        return verts, elems
    bad_elems = elems[all_on_surface]
    new_verts = np.mean(verts[bad_elems], axis=1, dtype=np.float32)
    new_elems = []
    for idx, (v0, v1, v2, v3) in enumerate(bad_elems, len(verts)):
        new_elems.append([v0, v1, v2, idx])
        new_elems.append([v0, v1, idx, v3])
        new_elems.append([v0, idx, v2, v3])
        new_elems.append([idx, v1, v2, v3])
    new_elems = np.array(new_elems, dtype=np.int32)
    verts = np.concatenate([verts, new_verts], axis=0)
    # remove the bad elements from the original elements
    elems = np.concatenate([elems[~all_on_surface], new_elems], axis=0)
    return verts, elems
