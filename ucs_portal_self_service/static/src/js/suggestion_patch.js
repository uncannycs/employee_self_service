/** @odoo-module **/

import { SuggestionService } from "@mail/core/common/suggestion_service";
import { patch } from "@web/core/utils/patch";

patch(SuggestionService.prototype, {
    getSupportedDelimiters(thread, env) {
        if (env?.inFrontendPortalChatter) {
            return [["@"], ["::"], [":", undefined, 2]];
        }
        return super.getSupportedDelimiters(...arguments);
    },
});
