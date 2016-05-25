#! /bin/python
import os

import rados
import rbd
from filesystem import FileSystem
from exception import *


# Need to define abstract class for Filesystem in a seperate file.


class CephBase:
    def __init__(self, rid, r_conf, pool):
        if not rid or not r_conf or not pool:
            raise file_system_exceptions.IncorrectConfigArgumentException()
        if not os.path.isfile(r_conf):
            raise file_system_exceptions.InvalidConfigFileException()
        self.rid = rid
        self.r_conf = r_conf
        self.pool = pool
        self.cluster = self.__init_cluster()
        self.ctx = self.__init_context()
        self.rbd = self.__init_rbd()
        self.is_debug = False

    def __repr__(self):
        return str([self.rid, self.r_conf, self.pool, self.is_debug])

    #
    # log in case of debug
    #
    def __str__(self):
        return 'rid = {0}, conf_file = {1}, pool = {2},' \
               'is_debug? = {3}, current images {4}' \
            .format(self.rid, self.r_conf,
                    self.pool, self.is_debug)

    def __init_context(self):
        return self.cluster.open_ioctx(self.pool.encode('utf-8'))

    def __init_cluster(self):
        cluster = rados.Rados(rados_id=self.rid, conffile=self.r_conf)
        cluster.connect()
        return cluster

    def __init_rbd(self):
        return rbd.RBD()

    def init_image(self, name, ctx=None, snapshot=None, read_only=False):
        if not ctx:
            ctx = self.ctx
        image_instance = rbd.Image(ctx, name, snapshot, read_only)
        ##return True We return True because we can already reference the image
        ##using the name as the key to the dict. The worklflos is something like
        return image_instance
        # define this function in the derivative class
        # to be specific for the call.

    # this is the teardown section, we undo things here
    def __td_context(self):
        self.ctx.close()

    def __td_cluster(self):
        self.cluster.shutdown()

    def tear_down(self):
        self.__td_context()
        self.__td_cluster()


class RBD(CephBase):
    def __init__(self, config):
        super(RBD, self).__init__(config['id'],
                       config['conf_file'],
                       config['pool'])

    def list_n(self):
        return self.rbd.list(self.ctx)

    def clone(self, p_name, p_snap, c_nm, p_ctx=None, c_ctx=None):
        try:
            if not p_ctx:
                p_ctx = self.ctx
            if not c_ctx:
                c_ctx = self.ctx
            self.rbd.clone(p_ctx, p_name, p_snap, c_ctx, c_nm, features=1)
            return True
        # Need to test whether image not found is raised for parent image
        except rbd.ImageNotFound as e:
            images = self.list_n()
            if p_name not in images:
                img_name = p_name
            else:
                img_name = p_snap
            raise file_system_exceptions.ImageNotFoundException(img_name)
        except rbd.ImageExists as e:
            raise file_system_exceptions.ImageExistsException(c_nm)
        # No Clue when will this be raised so not testing
        except rbd.FunctionNotSupported as e:
            raise file_system_exceptions.FunctionNotSupportedException()
        # No Clue when will this be raised so not testing
        except rbd.ArgumentOutOfRange as e:
            raise file_system_exceptions.ArgumentsOutOfRangeException()

    def remove(self, img_id, ctx=None):
        try:
            if not ctx:
                ctx = self.ctx
            self.rbd.remove(ctx, img_id)
            return True
        except rbd.ImageNotFound as e:
            raise file_system_exceptions.ImageNotFoundException(img_id)
        except rbd.ImageBusy as e:
            raise file_system_exceptions.ImageBusyException(img_id)
        except rbd.ImageHasSnapshots as e:
            raise file_system_exceptions.ImageHasSnapshotException(img_id)

    def write(self, img_id, data, offset):
        try:
            img = self.init_image(name=img_id)
            img.write(data, offset)
            img.close()
        except rbd.ImageNotFound as e:
            raise file_system_exceptions.ImageNotFoundException(img_id)

    def snap_image(self, img_id, name):
        try:

            snaps = self.list_snapshots(img_id)

            if name in snaps:
                raise file_system_exceptions.ImageExistsException(name)

            img = self.init_image(name=img_id)
            img.create_snap(name)
            img.close()
            return True
        # Was having issue ceph implemented work around
        except rbd.ImageExists:
            raise file_system_exceptions.ImageExistsException(img_id)
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)

    def list_snapshots(self, img_id):
        try:
            img = self.init_image(img_id)
            snap_list_iter = img.list_snaps()
            snap_list = [snap['name'] for snap in snap_list_iter]
            return snap_list
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)

    def remove_snapshots(self, img_id, name):
        try:
            img = self.init_image(name=img_id)
            img.remove_snap(name)
            img.close()
            return True
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)
        # Dont know how to raise this
        except rbd.ImageBusy:
            raise file_system_exceptions.ImageBusyException(img_id)

    def create_image(self, img_id, img_size, ctx=None):
        try:
            ctx = self.ctx
            self.rbd.create(ctx, img_id, img_size)
            return True
        except rbd.ImageExists as e:
            raise file_system_exceptions.ImageExistsException(img_id)
        except rbd.FunctionNotSupported as e:
            raise file_system_exceptions.FunctionNotSupportedException()

    def get_image(self, img_id):
        try:
            return self.init_image(img_id)
        except rbd.ImageNotFound as e:
            raise file_system_exceptions.ImageNotFoundException(img_id)
