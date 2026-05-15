using System;
using System.Collections;
using System.Net;
using XUnity.AutoTranslator.Plugin.Core.Endpoints;
using XUnity.AutoTranslator.Plugin.Core.Endpoints.Http;
using XUnity.AutoTranslator.Plugin.Core.Web;

namespace CustomTranslate
{
    public class CustomTranslateEndpoint : HttpEndpoint
    {
        private string _url = "http://127.0.0.1:56443";
        private string _currentUntranslatedText = "";

        public override string Id
        {
            get { return "CustomTranslate"; }
        }

        public override string FriendlyName
        {
            get { return "Hanhua LLM Translator"; }
        }

        public override int MaxTranslationsPerRequest
        {
            get { return 1; }
        }

        public override int MaxConcurrency
        {
            get { return 4; }
        }

        public override void Initialize(IInitializationContext context)
        {
            string configUrl = context.GetOrCreateSetting("Custom", "Url", "http://127.0.0.1:56443");
            if (!string.IsNullOrEmpty(configUrl))
                _url = configUrl;

            context.DisableCertificateChecksFor("*");
        }

        public override IEnumerator OnBeforeTranslate(IHttpTranslationContext context)
        {
            _currentUntranslatedText = context.UntranslatedText ?? "";
            yield break;
        }

        public override void OnCreateRequest(IHttpRequestCreationContext context)
        {
            var request = new XUnityWebRequest("POST", _url, _currentUntranslatedText);
            var headers = new WebHeaderCollection();
            headers["Content-Type"] = "text/plain; charset=utf-8";
            request.Headers = headers;
            context.Complete(request);
        }

        public override void OnInspectResponse(IHttpResponseInspectionContext context)
        {
            // No special inspection needed
        }

        public override void OnExtractTranslation(IHttpTranslationExtractionContext context)
        {
            string translation = null;

            var response = context.Response;
            if (response != null)
            {
                translation = response.Data;
            }

            if (!string.IsNullOrEmpty(translation))
            {
                context.Complete(translation.Trim());
            }
            else
            {
                // Fallback: return original text (shows Japanese untranslated)
                context.Complete(context.UntranslatedText);
            }
        }
    }
}
