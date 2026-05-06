from fastapi.testclient import TestClient


EMBED_POSTHOG_SNIPPET = """
<script>
    !function(t,e){var o,n,p,r;e.__SV||(window.posthog && window.posthog.__loaded)||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="kr Ar init $r zr ki Hr Yr qr capture calculateEventProperties Kr register register_once register_for_session unregister unregister_for_session rn getFeatureFlag getFeatureFlagPayload getFeatureFlagResult isFeatureEnabled reloadFeatureFlags updateFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSurveysLoaded onSessionId getSurveys getActiveMatchingSurveys renderSurvey displaySurvey cancelPendingSurvey canRenderSurvey canRenderSurveyAsync nn identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset setIdentity clearIdentity get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException addExceptionStep captureLog startExceptionAutocapture stopExceptionAutocapture loadToolbar get_property getSessionProperty tn Xr createPersonProfile setInternalOrTestUser en Br ln opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing get_explicit_consent_status is_capturing clear_opt_in_out_capturing Wr debug Ai Qr getPageViewId captureTraceFeedback captureTraceMetric Pr".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
    posthog.init('gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk', {
        api_host: 'https://emb.shopemberco.com', // your managed reverse proxy domain
        ui_host: 'https://us.posthog.com', // necessary because you're using a proxy
        defaults: '2026-01-30',
        person_profiles: 'identified_only',
    })
</script>
""".strip()


def _create_client(api_client: TestClient, *, name: str) -> str:
    response = api_client.post("/clients", json={"name": name, "industry": "Wellness"})
    assert response.status_code == 201
    return response.json()["id"]


def test_get_posthog_settings_defaults_to_empty_workspace_state(api_client: TestClient):
    client_id = _create_client(api_client, name="Analytics Empty Client")

    response = api_client.get(f"/clients/{client_id}/analytics/posthog")

    assert response.status_code == 200
    assert response.json() == {
        "hasSettings": False,
        "enabled": False,
        "projectApiKey": None,
        "apiHost": None,
        "uiHost": None,
        "defaults": "2026-01-30",
        "personProfiles": "identified_only",
        "sourceMode": "structured",
        "sourceSnippet": None,
        "resolvedTracking": None,
        "createdAt": None,
        "updatedAt": None,
    }


def test_parse_posthog_snippet_returns_normalized_workspace_config(api_client: TestClient):
    client_id = _create_client(api_client, name="Analytics Snippet Client")

    response = api_client.post(
        f"/clients/{client_id}/analytics/posthog/parse-snippet",
        json={"snippet": EMBED_POSTHOG_SNIPPET},
    )

    assert response.status_code == 200
    assert response.json() == {
        "hasSettings": False,
        "enabled": True,
        "projectApiKey": "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
        "apiHost": "https://emb.shopemberco.com",
        "uiHost": "https://us.posthog.com",
        "defaults": "2026-01-30",
        "personProfiles": "identified_only",
        "sourceMode": "snippet",
        "sourceSnippet": EMBED_POSTHOG_SNIPPET,
        "resolvedTracking": {
            "provider": "posthog",
            "mode": "public_funnel_runtime",
            "posthogProjectApiKey": "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
            "posthogApiHost": "https://emb.shopemberco.com",
            "posthogUiHost": "https://us.posthog.com",
            "posthogDefaults": "2026-01-30",
            "posthogPersonProfiles": "identified_only",
        },
        "createdAt": None,
        "updatedAt": None,
    }


def test_put_posthog_settings_persists_workspace_posthog_config(api_client: TestClient):
    client_id = _create_client(api_client, name="Analytics Save Client")

    save_response = api_client.put(
        f"/clients/{client_id}/analytics/posthog",
        json={
            "enabled": True,
            "projectApiKey": "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
            "apiHost": "https://emb.shopemberco.com",
            "uiHost": "https://us.posthog.com",
            "defaults": "2026-01-30",
            "personProfiles": "always",
            "sourceMode": "structured",
            "sourceSnippet": None,
        },
    )

    assert save_response.status_code == 200
    persisted = api_client.get(f"/clients/{client_id}/analytics/posthog")
    assert persisted.status_code == 200
    assert persisted.json()["hasSettings"] is True
    assert persisted.json()["personProfiles"] == "always"
    assert persisted.json()["apiHost"] == "https://emb.shopemberco.com"
    assert persisted.json()["resolvedTracking"] == {
        "provider": "posthog",
        "mode": "public_funnel_runtime",
        "posthogProjectApiKey": "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
        "posthogApiHost": "https://emb.shopemberco.com",
        "posthogUiHost": "https://us.posthog.com",
        "posthogDefaults": "2026-01-30",
        "posthogPersonProfiles": "always",
    }


def test_put_posthog_settings_rejects_invalid_api_host(api_client: TestClient):
    client_id = _create_client(api_client, name="Analytics Invalid Host Client")

    response = api_client.put(
        f"/clients/{client_id}/analytics/posthog",
        json={
            "enabled": True,
            "projectApiKey": "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
            "apiHost": "http://emb.shopemberco.com/path",
            "sourceMode": "structured",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "apiHost must be an https origin without a path."
