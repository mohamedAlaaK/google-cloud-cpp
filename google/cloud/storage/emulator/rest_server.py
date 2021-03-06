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

import flask
import httpbin
import utils
import gcs as gcs_type
from google.protobuf import json_format
from werkzeug import serving
from werkzeug.middleware.dispatcher import DispatcherMiddleware

db = None

# === DEFAULT ENTRY FOR REST SERVER === #
root = flask.Flask(__name__)
root.debug = True


@root.route("/")
def index():
    return "OK"


# === WSGI APP TO HANDLE JSON API === #
GCS_HANDLER_PATH = "/storage/v1"
gcs = flask.Flask(__name__)
gcs.debug = True


# === BUCKET === #


@gcs.route("/b", methods=["GET"])
def bucket_list():
    db.insert_test_bucket(None)
    project = flask.request.args.get("project")
    projection = flask.request.args.get("projection", "noAcl")
    fields = flask.request.args.get("fields", None)
    response = {
        "kind": "storage#buckets",
        "nextPageToken": "",
        "items": [
            bucket.rest() for bucket in db.list_bucket(flask.request, project, None)
        ],
    }
    return utils.common.filter_response_rest(response, projection, fields)


@gcs.route("/b", methods=["POST"])
def bucket_insert():
    db.insert_test_bucket(None)
    bucket, projection = gcs_type.bucket.Bucket.init(flask.request, None)
    fields = flask.request.args.get("fields", None)
    db.insert_bucket(flask.request, bucket, None)
    return utils.common.filter_response_rest(bucket.rest(), projection, fields)


@gcs.route("/b/<bucket_name>")
def bucket_get(bucket_name):
    db.insert_test_bucket(None)
    db.insert_test_bucket(None)
    bucket = db.get_bucket(flask.request, bucket_name, None)
    projection = utils.common.extract_projection(flask.request, 1, None)
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(bucket.rest(), projection, fields)


@gcs.route("/b/<bucket_name>", methods=["PUT"])
def bucket_update(bucket_name):
    db.insert_test_bucket(None)
    bucket = db.get_bucket(flask.request, bucket_name, None)
    bucket.update(flask.request, None)
    projection = utils.common.extract_projection(flask.request, 2, None)
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(bucket.rest(), projection, fields)


@gcs.route("/b/<bucket_name>", methods=["PATCH"])
def bucket_patch(bucket_name):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    bucket.patch(flask.request, None)
    projection = utils.common.extract_projection(flask.request, 2, None)
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(bucket.rest(), projection, fields)


@gcs.route("/b/<bucket_name>", methods=["DELETE"])
def bucket_delete(bucket_name):
    db.delete_bucket(flask.request, bucket_name, None)
    return ""


# === BUCKET ACL === #


@gcs.route("/b/<bucket_name>/acl")
def bucket_acl_list(bucket_name):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    response = {"kind": "storage#bucketAccessControls", "items": []}
    for acl in bucket.metadata.acl:
        acl_rest = json_format.MessageToDict(acl)
        acl_rest["kind"] = "storage#bucketAccessControl"
        response["items"].append(acl_rest)
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(response, None, fields)


@gcs.route("/b/<bucket_name>/acl", methods=["POST"])
def bucket_acl_insert(bucket_name):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    acl = bucket.insert_acl(flask.request, None)
    response = json_format.MessageToDict(acl)
    response["kind"] = "storage#bucketAccessControl"
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(response, None, fields)


@gcs.route("/b/<bucket_name>/acl/<entity>")
def bucket_acl_get(bucket_name, entity):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    acl = bucket.get_acl(entity, None)
    response = json_format.MessageToDict(acl)
    response["kind"] = "storage#bucketAccessControl"
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(response, None, fields)


@gcs.route("/b/<bucket_name>/acl/<entity>", methods=["PUT"])
def bucket_acl_update(bucket_name, entity):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    acl = bucket.update_acl(flask.request, entity, None)
    response = json_format.MessageToDict(acl)
    response["kind"] = "storage#bucketAccessControl"
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(response, None, fields)


@gcs.route("/b/<bucket_name>/acl/<entity>", methods=["PATCH"])
def bucket_acl_patch(bucket_name, entity):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    acl = bucket.patch_acl(flask.request, entity, None)
    response = json_format.MessageToDict(acl)
    response["kind"] = "storage#bucketAccessControl"
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(response, None, fields)


@gcs.route("/b/<bucket_name>/acl/<entity>", methods=["DELETE"])
def bucket_acl_delete(bucket_name, entity):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    bucket.delete_acl(entity, None)
    return ""


@gcs.route("/b/<bucket_name>/defaultObjectAcl")
def bucket_default_object_acl_list(bucket_name):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    response = {"kind": "storage#objectAccessControls", "items": []}
    for acl in bucket.metadata.default_object_acl:
        acl_rest = json_format.MessageToDict(acl)
        acl_rest["kind"] = "storage#objectAccessControl"
        response["items"].append(acl_rest)
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(response, None, fields)


@gcs.route("/b/<bucket_name>/defaultObjectAcl", methods=["POST"])
def bucket_default_object_acl_insert(bucket_name):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    acl = bucket.insert_default_object_acl(flask.request, None)
    response = json_format.MessageToDict(acl)
    response["kind"] = "storage#objectAccessControl"
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(response, None, fields)


@gcs.route("/b/<bucket_name>/defaultObjectAcl/<entity>")
def bucket_default_object_acl_get(bucket_name, entity):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    acl = bucket.get_default_object_acl(entity, None)
    response = json_format.MessageToDict(acl)
    response["kind"] = "storage#objectAccessControl"
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(response, None, fields)


@gcs.route("/b/<bucket_name>/defaultObjectAcl/<entity>", methods=["PUT"])
def bucket_default_object_acl_update(bucket_name, entity):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    acl = bucket.update_default_object_acl(flask.request, entity, None)
    response = json_format.MessageToDict(acl)
    response["kind"] = "storage#objectAccessControl"
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(response, None, fields)


@gcs.route("/b/<bucket_name>/defaultObjectAcl/<entity>", methods=["PATCH"])
def bucket_default_object_acl_patch(bucket_name, entity):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    acl = bucket.patch_default_object_acl(flask.request, entity, None)
    response = json_format.MessageToDict(acl)
    response["kind"] = "storage#bucketAccessControl"
    fields = flask.request.args.get("fields", None)
    return utils.common.filter_response_rest(response, None, fields)


@gcs.route("/b/<bucket_name>/defaultObjectAcl/<entity>", methods=["DELETE"])
def bucket_default_object_acl_delete(bucket_name, entity):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    bucket.delete_default_object_acl(entity, None)
    return ""


@gcs.route("/b/<bucket_name>/notificationConfigs")
def bucket_notification_list(bucket_name):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    response = {"kind": "storage#notifications", "items": []}
    for notification in bucket.notifications.values():
        response["items"].append(
            json_format.MessageToDict(notification, preserving_proto_field_name=True)
        )
    return response


@gcs.route("/b/<bucket_name>/notificationConfigs", methods=["POST"])
def bucket_notification_insert(bucket_name):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    notification = bucket.insert_notification(flask.request, None)
    response = json_format.MessageToDict(notification, preserving_proto_field_name=True)
    response["kind"] = "storage#notification"
    return response


@gcs.route("/b/<bucket_name>/notificationConfigs/<notification_id>")
def bucket_notification_get(bucket_name, notification_id):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    notification = bucket.get_notification(notification_id, None)
    response = json_format.MessageToDict(notification, preserving_proto_field_name=True)
    response["kind"] = "storage#notification"
    return response


@gcs.route("/b/<bucket_name>/notificationConfigs/<notification_id>", methods=["DELETE"])
def bucket_notification_delete(bucket_name, notification_id):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    bucket.delete_notification(notification_id, None)
    return ""


@gcs.route("/b/<bucket_name>/iam")
def bucket_get_iam_policy(bucket_name):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    response = json_format.MessageToDict(bucket.iam_policy)
    response["kind"] = "storage#policy"
    return response


@gcs.route("/b/<bucket_name>/iam", methods=["PUT"])
def bucket_set_iam_policy(bucket_name):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    bucket.set_iam_policy(flask.request, None)
    response = json_format.MessageToDict(bucket.iam_policy)
    response["kind"] = "storage#policy"
    return response


@gcs.route("/b/<bucket_name>/iam/testPermissions")
def bucket_test_iam_permissions(bucket_name):
    db.get_bucket(flask.request, bucket_name, None)
    permissions = flask.request.args.getlist("permissions")
    result = {"kind": "storage#testIamPermissionsResponse", "permissions": permissions}
    return result


@gcs.route("/b/<bucket_name>/lockRetentionPolicy", methods=["POST"])
def bucket_lock_retention_policy(bucket_name):
    bucket = db.get_bucket(flask.request, bucket_name, None)
    bucket.metadata.retention_policy.is_locked = True
    return bucket.rest()


# === SERVER === #


server = DispatcherMiddleware(root, {"/httpbin": httpbin.app, GCS_HANDLER_PATH: gcs})


def run(port, database):
    global db
    db = database
    serving.run_simple(
        "localhost", int(port), server, use_reloader=False, threaded=True
    )
