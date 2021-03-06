# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Implement a class to simulate GCS object."""

import utils
import datetime
import random
import crc32c
import base64
import hashlib
import struct
import simdjson
from google.protobuf import field_mask_pb2, json_format
from google.cloud.storage_v1.proto import storage_resources_pb2 as resources_pb2


class Object:
    modifiable_fields = [
        "content_encoding",
        "content_disposition",
        "cache_control",
        "acl",
        "content_language",
        "content_type",
        "storage_class",
        "kms_key_name",
        "temporary_hold",
        "retention_expiration_time",
        "metadata",
        "event_based_hold",
        "customer_encryption",
    ]

    def __init__(self, metadata, media, bucket):
        self.metadata = metadata
        self.media = media
        self.bucket = bucket

    @classmethod
    def __insert_predefined_acl(cls, metadata, bucket, predefined_acl, context):
        if predefined_acl == "" or predefined_acl == 0:
            return
        if bucket.iam_configuration.uniform_bucket_level_access.enabled:
            utils.error.invalid(
                "Predefined ACL with uniform bucket level access enabled", context
            )
        acls = utils.acl.compute_predefined_object_acl(
            metadata.bucket, metadata.name, metadata.generation, predefined_acl, context
        )
        del metadata.acl[:]
        metadata.acl.extend(acls)

    @classmethod
    def init(cls, request, metadata, media, bucket, is_destination, context):
        timestamp = datetime.datetime.now(datetime.timezone.utc)
        metadata.generation = random.getrandbits(63)
        metadata.metageneration = 1
        metadata.id = "%s/o/%s#%d" % (
            metadata.bucket,
            metadata.name,
            metadata.generation,
        )
        metadata.size = len(media)
        actual_md5Hash = base64.b64encode(hashlib.md5(media).digest()).decode("utf-8")
        if metadata.md5_hash != "" and actual_md5Hash != metadata.md5_hash:
            utils.error.mismatch("md5Hash", metadata.md5_hash, actual_md5Hash, context)
        actual_crc32c = crc32c.crc32(media)
        if metadata.HasField("crc32c") and actual_crc32c != metadata.crc32c.value:
            utils.error.mismatch(
                "crc32c", metadata.crc32c.value, actual_crc32c, context
            )
        metadata.md5_hash = actual_md5Hash
        metadata.crc32c.value = actual_crc32c
        metadata.time_created.FromDatetime(timestamp)
        metadata.updated.FromDatetime(timestamp)
        metadata.owner.entity = utils.acl.get_object_entity("OWNER", context)
        metadata.owner.entity_id = hashlib.md5(
            metadata.owner.entity.encode("utf-8")
        ).hexdigest()
        predefined_acl = utils.acl.extract_predefined_acl(
            request, is_destination, context
        )
        cls.__insert_predefined_acl(metadata, bucket, predefined_acl, context)
        return cls(metadata, media, bucket)

    @classmethod
    def init_dict(cls, request, metadata, media, bucket, is_destination):
        metadata = json_format.ParseDict(metadata, resources_pb2.Object())
        return cls.init(metadata, media, request, bucket, is_destination, None)

    @classmethod
    def init_media(cls, request, bucket):
        object_name = request.args.get("name", None)
        media = request.data
        if object_name is None:
            utils.error.missing("name", None)
        metadata = {
            "bucket": bucket.name,
            "name": object_name,
            "metadata": {"x_testbench_upload": "simple"},
        }
        return cls.init_dict(request, metadata, media, bucket, False)

    @classmethod
    def init_multipart(cls, request, bucket):
        metadata, media_headers, media = utils.common.parse_multipart(request)
        metadata["name"] = request.args.get("name", metadata.get("name", None))
        if metadata["name"] is None:
            utils.error.missing("name", None)
        if (
            metadata.get("contentType") is not None
            and media_headers.get("content-type") is not None
            and metadata.get("contentType") != media_headers.get("content-type")
        ):
            utils.error.mismatch(
                "Content-Type",
                media_headers.get("content-type"),
                metadata.get("contentType"),
            )
        metadata["bucket"] = bucket.name
        if "contentType" not in metadata:
            metadata["contentType"] = media_headers.get("content-type")
        metadata["metadata"] = (
            {} if "metadata" not in metadata else metadata["metadata"]
        )
        metadata["metadata"]["x_testbench_upload"] = "multipart"
        if "md5Hash" in metadata:
            metadata["metadata"]["x_testbench_md5"] = metadata["md5Hash"]
            metadata["md5Hash"] = metadata["md5Hash"]
        if "crc32c" in metadata:
            metadata["metadata"]["x_testbench_crc32c"] = metadata["crc32c"]
            metadata["crc32c"] = struct.unpack(
                ">I", base64.b64decode(metadata["crc32c"].encode("utf-8"))
            )[0]
        return cls.init_dict(request, metadata, media, bucket, False)

    # === METADATA === #

    def __update_metadata(self, source, update_mask):
        if update_mask is None:
            update_mask = field_mask_pb2.FieldMask(paths=Object.modifiable_fields)
        update_mask.MergeMessage(source, self.metadata, True, True)
        if self.bucket.versioning.enabled:
            self.metadata.metageneration += 1
        self.metadata.updated.FromDatetime(datetime.datetime.now())

    def update(self, request, context):
        metadata = None
        if context is not None:
            metadata = request.metadata
        else:
            metadata = json_format.ParseDict(
                self.__preprocess_rest(simdjson.loads(request.data)),
                resources_pb2.Bucket(),
            )
        self.__update_metadata(metadata, None)
        self.__insert_predefined_acl(
            metadata,
            self.bucket,
            utils.acl.extract_predefined_acl(request, False, context),
            context,
        )

    def patch(self, request, context):
        update_mask = field_mask_pb2.FieldMask()
        metadata = None
        if context is not None:
            metadata = request.metadata
            update_mask = request.update_mask
        else:
            data = simdjson.loads(request.data)
            if "metadata" in data:
                if data["metadata"] is None:
                    self.metadata.metadata.clear()
                else:
                    for key, value in data["metadata"].items():
                        if value is None:
                            self.metadata.metadata.pop(key, None)
                        else:
                            self.metadata.metadata[key] = value
            data.pop("metadata", None)
            metadata = json_format.ParseDict(data, resources_pb2.Bucket())
            paths = set()
            for key in utils.common.nested_key(data):
                key = utils.common.to_snake_case(key)
                head = key
                for i, c in enumerate(key):
                    if c == "." or c == "[":
                        head = key[0:i]
                        break
                if head in Object.modifiable_fields:
                    if "[" in key:
                        paths.add(head)
                    else:
                        paths.add(key)
            update_mask = field_mask_pb2.FieldMask(paths=list(paths))
        self.__update_metadata(metadata, update_mask)
        self.__insert_predefined_acl(
            metadata,
            self.bucket,
            utils.acl.extract_predefined_acl(request, False, context),
            context,
        )

    # === ACL === #

    def __search_acl(self, entity, must_exist, context):
        entity = utils.acl.get_canonical_entity(entity)
        for i in range(len(self.metadata.acl)):
            if self.metadata.acl[i].entity == entity:
                return i
        if must_exist:
            utils.error.notfound("ACL %s" % entity, context)

    def __upsert_acl(self, entity, role, update_only, context):
        # For simplicity, we treat `insert`, `update` and `patch` ACL the same way.
        index = self.__search_acl(entity, update_only, context)
        acl = utils.acl.create_object_acl(
            self.metadata.bucket,
            self.metadata.name,
            self.metadata.generation,
            entity,
            role,
            context,
        )
        if index is not None:
            self.metadata.acl[index].CopyFrom(acl)
            return self.metadata.acl[index]
        else:
            self.metadata.acl.append(acl)
            return acl

    def get_acl(self, entity, context):
        index = self.__search_acl(entity, True, context)
        return self.metadata.acl[index]

    def insert_acl(self, request, context):
        entity, role = "", ""
        if context is not None:
            entity, role = (
                request.object_access_control.entity,
                request.object_access_control.role,
            )
        else:
            payload = simdjson.loads(request.data)
            entity, role = payload["entity"], payload["role"]
        return self.__upsert_acl(entity, role, False, context)

    def update_acl(self, request, entity, context):
        role = ""
        if context is not None:
            role = request.object_access_control.role
        else:
            payload = simdjson.loads(request.data)
            role = payload["role"]
        return self.__upsert_acl(entity, role, True, context)

    def patch_acl(self, request, entity, context):
        role = ""
        if context is not None:
            role = request.object_access_control.role
        else:
            payload = simdjson.loads(request.data)
            role = payload["role"]
        return self.__upsert_acl(entity, role, True, context)

    def delete_acl(self, entity, context):
        del self.metadata.acl[self.__search_acl(entity, True, context)]
