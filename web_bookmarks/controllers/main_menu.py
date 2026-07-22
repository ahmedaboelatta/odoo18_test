from odoo import http
from odoo.http import request, route


class MainMenuController(http.Controller):

    @route("/web_bookmarks/bookmark", methods=["POST"], type="json", auth="user")
    def get_bookmarks_by_user(self, **kwargs):
        return request.env["menu.bookmark"].search_read([("user_id", "=", request.env.uid)], [])

    @route("/web_bookmarks/bookmark/add", methods=["POST"], type="json", auth="user")
    def add_bookmark(self, **kwargs):
        return request.env["menu.bookmark"].create(kwargs.get("bookmark"))
