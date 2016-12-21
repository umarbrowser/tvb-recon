# -*- coding: utf-8 -*-

import os
import numpy
import scipy.ndimage
from bnm.recon.algo.service.annotation import AnnotationService
from bnm.recon.io.volume import VolumeIO
from bnm.recon.model.volume import Volume
from scipy.spatial.distance import pdist, squareform


class VolumeService(object):
    def __init__(self):
        self.annotation_service = AnnotationService()
        self.volume_io = VolumeIO()

    # Separate the voxels of the outer surface of a structure, from the inner ones
    # Default behavior: surface voxels retain their label, inner voxels get the label 0,
    # and the input file is overwritten by the output
    def vol_to_ext_surf_vol(self, in_vol_path, labels=None, hemi=None, out_vol_path=None, labels_surf=None,
                            labels_inner='0'):

        labels, number_of_labels = self.annotation_service.read_input_labels(labels=labels, hemi=hemi)
        # Set the labels for the surfaces
        if labels_surf is None:
            labels_surf = labels
        else:
            # Read the surface labels and make sure there is one for each label
            labels_surf = numpy.array(labels_surf.split()).astype('i')
            if len(labels_surf) == 1:
                labels_surf = numpy.repeat(labels_inner, number_of_labels).tolist()
            elif len(labels_surf) != number_of_labels:
                print "Output labels for surface voxels are neither of length 1 nor of length equal to the one of " \
                      "target labels"
                return
            else:
                labels_surf = labels_surf.tolist()
        # Read the inner, non-surface labels
        labels_inner = numpy.array(labels_inner.split()).astype('i')
        # ...and make sure there is one for each label
        if len(labels_inner) == 1:
            labels_inner = numpy.repeat(labels_inner, number_of_labels).tolist()
        elif len(labels_inner) != number_of_labels:
            print "Output labels for inner voxels are neither of length 1 nor of length equal to the one of the " \
                  "target labels"
            return
        else:
            labels_inner = labels_inner.tolist()

        # Read the input volume...
        volume = self.volume_io.read(in_vol_path)

        # Neigbors' grid sharing a face
        border_grid = numpy.c_[numpy.identity(3), -numpy.identity(3)].T.astype('i')
        n_border = 6

        out_volume = Volume(numpy.array(volume.data), volume.affine_matrix, volume.header)

        # Initialize output indexes
        out_ijk = []

        for label_index in range(number_of_labels):
            current_label = labels[label_index]
            # Get the indexes of all voxels of this label:
            label_volxels_i, label_voxels_j, label_voxels_k = numpy.where(volume.data == current_label)
            # and for each voxel
            for voxel_index in range(label_volxels_i.size):
                # indexes of this voxel:
                current_voxel_i, current_voxel_j, current_voxel_k = label_volxels_i[voxel_index], label_voxels_j[voxel_index], label_voxels_k[voxel_index]
                # Create the neighbors' grid sharing a face
                ijk_grid = border_grid + numpy.tile(numpy.array([current_voxel_i, current_voxel_j, current_voxel_k]), (n_border, 1))
                # Remove voxels outside the image
                indices_inside_image = numpy.all([(ijk_grid[:, 0] >= 0), (ijk_grid[:, 0] < volume.dimensions[0]),
                                               (ijk_grid[:, 1] >= 0), (ijk_grid[:, 1] < volume.dimensions[1]),
                                               (ijk_grid[:, 2] >= 0), (ijk_grid[:, 2] < volume.dimensions[2])],
                                              axis=0)
                ijk_grid = ijk_grid[indices_inside_image, :]
                try:
                    # If all face neighbors are of the same label...
                    if numpy.all(volume.data[ijk_grid[:, 0], ijk_grid[:, 1], ijk_grid[:, 2]] == numpy.tile(
                            volume.data[current_voxel_i, current_voxel_j, current_voxel_k],
                            (n_border, 1))):
                        # ...set this voxel to the corresponding inner target label
                        out_volume.data[current_voxel_i, current_voxel_j, current_voxel_k] = labels_inner[label_index]
                    else:
                        # ...set this voxel to the corresponding surface target label
                        out_volume.data[current_voxel_i, current_voxel_j, current_voxel_k] = labels_surf[label_index]
                        out_ijk.append([current_voxel_i, current_voxel_j, current_voxel_k])
                except ValueError:  # empty grid
                    print "Error at voxel (" + str(current_voxel_i) + "," + str(current_voxel_j) + "," + str(current_voxel_k) + ") of label " + str(current_label) + ":"
                    print "It appears to have no common-face neighbors inside the image!"
                    return

        if out_vol_path is None:
            out_vol_path = in_vol_path

        self.volume_io.write(out_vol_path, out_volume)

        # save the output indexes that survived masking
        out_ijk = numpy.vstack(out_ijk)
        filepath = os.path.splitext(out_vol_path)[0]
        numpy.save(filepath + "-idx.npy", out_ijk)
        numpy.savetxt(filepath + "-idx.txt", out_ijk, fmt='%d')

    # Identify the voxels that are neighbors within a voxel distance vn, to a mask volume,
    # with a mask threshold of th
    # Default behavior: we assume a binarized mask and set th=0.999,
    # no neighbors search, only looking at the exact voxel position, i.e., vn=0.
    # and accepted voxels retain their label, whereas rejected ones get a label of 0
    def mask_to_vol(self, in_vol_path, mask_vol_path, out_vol_path=None, labels=None, hemi=None, vol2mask_path=None, vn=1, th=0.999, labels_mask=None, labels_nomask='0'):
        # Set the target labels:
        labels, number_of_labels = self.annotation_service.read_input_labels(labels=labels, hemi=hemi)
        # Set the labels for the selected voxels
        if labels_mask is None:
            labels_mask = labels

        else:
            # Read the labels and make sure there is one for each label
            labels_mask = numpy.array (labels_mask.split()).astype('i')

            if len(labels_mask) == 1:
                labels_mask = numpy.repeat(labels_mask, number_of_labels).tolist()

            elif len(labels_mask) != number_of_labels:
                print "Output labels for selected voxels are neither of length 1 nor of length equal to the one of " \
                      "target labels"
                return

            else:
                labels_mask = labels_mask.tolist()

        # Read the excluded labels and make sure there is one for each label
        labels_nomask = numpy.array(labels_nomask.split()).astype('i')
        if len(labels_nomask) == 1:
            labels_nomask = numpy.repeat(labels_nomask, number_of_labels).tolist()

        elif len(labels_nomask) != number_of_labels:
            print "Output labels for excluded voxels are neither of length 1 nor of length equal to the one of the " \
                  "target labels"
            return

        else:
            labels_nomask = labels_nomask.tolist()

        volume = self.volume_io.read(in_vol_path)

        mask_vol = self.volume_io.read(mask_vol_path)

        # Compute the transform from vol ijk to mask ijk:
        ijk2ijk = numpy.identity(4)

        # If vol and mask are not in the same space:
        if os.path.exists(str(vol2mask_path)):
            # read the xyz2xyz transform and apply it to the inverse mask affine transform to get an ijk2ijk transform.
            xyz2xyz = numpy.loadtxt(vol2mask_path)
            ijk2ijk = volume.affine_matrix.dot(numpy.dot(xyz2xyz, numpy.linalg.inv(mask_vol.affine_matrix)))

        # Construct a grid template of voxels +/- vn voxels around each ijk voxel, sharing at least a corner
        grid = numpy.meshgrid(range(-vn, vn + 1, 1), range(-vn, vn + 1, 1), range(-vn, vn + 1, 1), indexing='ij')
        grid = numpy.c_[numpy.array(grid[0]).flatten(), numpy.array(grid[1]).flatten(), numpy.array(grid[2]).flatten()]
        n_grid = grid.shape[0]

        out_volume = Volume(numpy.array(volume.data), volume.affine_matrix, volume.header)

        # Initialize output indexes
        out_ijk = []

        # For each target label:
        for label_index in range(number_of_labels):
            current_label = labels[label_index]
            # Get the indexes of all voxels of this label:
            label_voxels_i, label_voxels_j, label_voxels_k = numpy.where(volume.data == current_label)

            for voxel_index in range(label_voxels_i.size):
                current_voxel_i, current_voxel_j, current_voxel_k = label_voxels_i[voxel_index], label_voxels_j[voxel_index], label_voxels_k[voxel_index]
                # TODO if necessary: deal with voxels at the edge of the image, such as brain stem ones...
                #     if any([(i==0), (i==mask_shape[0]-1),(j==0), (j==mask_shape[0]-1),(k==0), (k==mask_shape[0]-1)]):
                #               mask_shape[i,j,k]=0
                #               continue

                # ...get the corresponding voxel in the mask volume:
                ijk = numpy.round(ijk2ijk.dot(numpy.array([current_voxel_i, current_voxel_j, current_voxel_k, 1]))[:3]).astype('i')

                # Make sure this point is within image limits
                for cc in range(3):
                    if ijk[cc] < 0:
                        ijk[cc] = 0

                    elif ijk[cc] >= mask_vol.dimensions[cc]:
                        ijk[cc] = mask_vol.dimensions[cc] - 1

                # If this is a voxel to keep, set it so...
                if mask_vol.data[ijk[0], ijk[1], ijk[2]] >= th:
                    out_volume.data[current_voxel_i, current_voxel_j, current_voxel_k] = labels_mask[label_index]
                    out_ijk.append([current_voxel_i, current_voxel_j, current_voxel_k])

                elif vn > 0:
                    # If not, and as long as vn>0 check whether any of its vn neighbors is a mask voxel.
                    # Generate the specific grid centered at the vertex ijk
                    ijk_grid = grid + numpy.tile(ijk, (n_grid, 1))

                    # Remove voxels outside the mask volume
                    indexes_within_limits = numpy.all([(ijk_grid[:, 0] >= 0), (ijk_grid[:, 0] < mask_vol.dimensions[0]),
                                                       (ijk_grid[:, 1] >= 0), (ijk_grid[:, 1] < mask_vol.dimensions[1]),
                                                       (ijk_grid[:, 2] >= 0),
                                                       (ijk_grid[:, 2] < mask_vol.dimensions[2])],
                                                      axis=0)
                    ijk_grid = ijk_grid[indexes_within_limits, :]

                    try:
                        # If none of these points is a mask point:
                        if (mask_vol.data[ijk_grid[:, 0], ijk_grid[:, 1], ijk_grid[:, 2]] < th).all():
                            out_volume.data[current_voxel_i, current_voxel_j, current_voxel_k] = labels_nomask[label_index]

                        else:  # if any of them is a mask point:
                            out_volume.data[current_voxel_i, current_voxel_j, current_voxel_k] = labels_mask[label_index]
                            out_ijk.append([current_voxel_i, current_voxel_j, current_voxel_k])

                    except ValueError:  # empty grid
                        print "Error at voxel (" + str(current_voxel_i) + "," + str(current_voxel_j) + "," + str(current_voxel_k) + "):"
                        print "It appears to have no common-face neighbors inside the image!"
                        return

                else:
                    out_volume.data[current_voxel_i, current_voxel_j, current_voxel_k] = labels_nomask[label_index]

        if out_vol_path == None:
            out_vol_path = in_vol_path

        self.volume_io.write(out_vol_path, out_volume)

        # Save the output indexes that survived masking
        out_ijk = numpy.vstack(out_ijk)
        filepath = os.path.splitext(out_vol_path)[0]
        numpy.save(filepath + "-idx.npy", out_ijk)
        numpy.savetxt(filepath + "-idx.txt", out_ijk, fmt='%d')

    # Label one nifti with its dilation, cf seeg-ct.sh
    def label_with_dilation(self, to_label_nii_fname, dilated_nii_fname, out_nii_fname):
        # TODO could make dilation with ndimage also.
        mask = self.volume_io.read(to_label_nii_fname)
        dil_mask = self.volume_io.read(dilated_nii_fname)

        lab, n = scipy.ndimage.label(dil_mask.data)
        mask.data *= lab
        print('[label_with_dilation] %d objects found.' % (n,))

        self.volume_io.write(out_nii_fname, mask)

    #TODO for Paula: Merge with the next one
    # Rewrite label volume to have contiguous values like mrtrix' labelconfig.
    def simple_label_config(self, in_aparc_path, out_path):
        aparc = self.volume_io.read(in_aparc_path)
        unique_data = numpy.unique(aparc.data)
        unique_data_map = numpy.r_[:unique_data.max() + 1]
        unique_data_map[unique_data] = numpy.r_[:unique_data.size]
        aparc.data = unique_data_map[aparc.data]
        self.volume_io.write(out_path, aparc)

    # Make label volume from tckmap output.
           def label_vol_from_tdi(self, tdi_nii_fname, out_fname, lo=0.5):
            nii_volume = self.volume_io.read(tdi_nii_fname)

            tdi_volume = Volume(nii_volume.data.copy(), nii_volume.affine_matrix, nii_volume.header)
            # and mask them to get the voxels of tract ends
            mask = tdi_volume.data > lo
            # (all other voxels ->0)
            tdi_volume.data[~mask] = 0
            # Assign them with integer labels starting from 1
            tdi_volume.data[mask] = numpy.r_[1:mask.sum() + 1]

        self.volume_io.write(out_fname, tdi_volume)

    # It removes network nodes with zero connectivity, and returns a symmetric connectivity matrix
    # Inputs:
    #    - the tdi_lbl.nii volume path
    #    -a .csv connectivity file path, output of Mrtrix3 tck2connectome
    # Outputs:
    #   - the symmetric no-zero-connections connectivity matrix saved as .npy
    #   - the tdi_lbl.nii volume with the removed voxel nodes to 0 and the labels
    #    updated
    # Optionally: if the tract length matrix is in the input, it is also processed
    def remove_zero_connectivity_nodes(self, node_volume_path, connectivity_matrix_path, tract_length_path=None):
        node_volume = self.volume_io.read(node_volume_path)
        out_volume = Volume(node_volume.data, node_volume.affine_matrix, node_volume.header)

        connectivity = numpy.array(numpy.genfromtxt(connectivity_matrix_path, dtype='int64'))

        # Make it symmetric:
        connectivity = connectivity + connectivity.T

        connectivity_row_sum = numpy.sum(connectivity, axis=0)
        nodes_to_keep_indices = connectivity_row_sum > 0

        # Select only the specified columns and rows from the connectivity matrix:
        connectivity = connectivity[nodes_to_keep_indices, :][:, nodes_to_keep_indices]

        numpy.save(os.path.splitext(connectivity_matrix_path)[0] + ".npy", connectivity)
        numpy.savetxt(connectivity_matrix_path, connectivity)

        if os.path.exists(str(tract_length_path)):
            connectivity = numpy.array(numpy.genfromtxt(tract_length_path, dtype='int64'))
            connectivity = connectivity[nodes_to_keep_indices, :][:, nodes_to_keep_indices]

            numpy.save(os.path.splitext(tract_length_path)[0] + ".npy", connectivity)
            numpy.savetxt(tract_length_path, connectivity)

        else:
            print tract_length_path + " is not a valid path"

        nodes_to_remove_indices, = numpy.where(~nodes_to_keep_indices)
        nodes_to_remove_indices = nodes_to_remove_indices + 1
        nodes_to_keep_number = connectivity.shape[0]

        for iR in nodes_to_remove_indices:
            out_volume.data[out_volume.data == iR] = 0

        # Update remaining indexes
        out_volume.data[out_volume.data > 0] = numpy.r_[1:(nodes_to_keep_number + 1)]

        self.volume_io.write(node_volume_path, out_volume)


