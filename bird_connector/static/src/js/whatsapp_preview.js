odoo.define('bird_connector.WhatsappPreviewPanel', function (require) {
    "use strict";

    const {
        Component,
        useState,
        onWillStart,
    } = require('owl.Component');
    const {
        useService,
    } = require('web.utils');
    const { _t } = require('web.core');

    const qweb = require('web.qweb');

    class WhatsAppPreviewPanel extends Component {
        async setup() {
            this.__owlProps = this.__owlProps || {};
            this.state = useState({
                headerImage: this.props.headerImage || '',
                bodyText: this.props.bodyText || '',
                footerText: this.props.footerText || '',
                buttonUrl: this.props.buttonUrl || '',
                buttonText: this.props.buttonText || 'اطلب الآن',
            });

            onWillStart(async () => {
                if (this.props.record) {
                    this.state.headerImage = this.props.record.data.header_image_url || '';
                    this.state.bodyText = this.props.record.data.body_text || '';
                    this.state.footerText = this.props.record.data.footer_text || '';
                    this.state.buttonUrl = this.props.record.data.button_url || '';
                    this.state.buttonText = this.props.record.data.button_text || 'اطلب الآن';
                }
            });
        }
    }

    WhatsAppPreviewPanel.template = 'bird_connector.WhatsappPreviewPanel';
    WhatsAppPreviewPanel.defaultProps = {
        record: undefined,
        headerImage: '',
        bodyText: '',
        footerText: '',
        buttonUrl: '',
        buttonText: 'اطلب الآن',
    };

    const WhatsappPreviewRegistry = {
        FieldWhatsappPreview: Component.extend(WhatsAppPreviewPanel),
    };

    core.action_registry.add('bird_connector.WhatsappPreviewPanel', WhatsappPreviewRegistry.FieldWhatsappPreview);

    return { FieldWhatsappPreview: WhatsappPreviewRegistry.FieldWhatsappPreview };
});
