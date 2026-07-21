# frozen_string_literal: true

require 'json'
require 'net/http'
require 'uri'
require 'openssl'

###############################################################################
# OpenVox ENC Bolt Inventory — pure library used by resolve_reference task
#
# Extracted so unit tests can exercise token handling, HTTP error mapping,
# group filtering, deduplication, and run-as injection without invoking Bolt.
###############################################################################

module OpenvoxEnc
  module Inventory
    DEFAULT_API_URL    = 'https://localhost:4567'
    DEFAULT_TOKEN_FILE = '/etc/puppetlabs/bolt/.bolt_token'
    DEFAULT_TRANSPORT  = 'ssh'
    DEFAULT_USER       = 'bolt'

    class << self
      # Resolve Bearer token from explicit param or token file.
      # Returns a stripped string or nil.
      def resolve_token(api_token: nil, token_file: DEFAULT_TOKEN_FILE)
        token = api_token
        if (token.nil? || token.to_s.empty?) && token_file && File.exist?(token_file)
          begin
            token = File.read(token_file).strip
          rescue StandardError
            token = nil
          end
        end
        token = token.to_s.strip
        token.empty? ? nil : token
      end

      # Build Bolt target hashes from an ENC inventory API payload.
      #
      # @param inventory [Hash] parsed JSON from /api/enc/inventory/bolt
      # @param group_filter [String, nil] only include this ENC group name
      # @param transport [String] Bolt transport name (default ssh)
      # @param run_as [String, nil] optional run-as user injected into transport config
      # @param run_as_command [Array, nil] optional run-as-command array
      # @return [Array<Hash>]
      def build_targets(inventory,
                        group_filter: nil,
                        transport: DEFAULT_TRANSPORT,
                        run_as: nil,
                        run_as_command: nil)
        targets = []
        seen = {}
        groups = inventory.is_a?(Hash) ? (inventory['groups'] || []) : []

        groups.each do |grp|
          next unless grp.is_a?(Hash)

          grp_name = grp['name']
          grp_targets = grp['targets'] || []

          # Skip PuppetDB / nested plugin groups (Bolt handles those natively)
          if grp_targets.is_a?(Array) && grp_targets.any? { |t| t.is_a?(Hash) && t.key?('_plugin') }
            next
          end

          next if group_filter && grp_name != group_filter

          Array(grp_targets).each do |certname|
            next if certname.is_a?(Hash) # plugin references
            next if seen[certname]       # dedupe across groups

            seen[certname] = true
            target = {
              'uri'  => certname,
              'name' => certname,
              'config' => {
                'transport' => transport,
                transport   => { 'host-key-check' => false },
              },
              'vars' => {
                'enc_groups' => [],
              },
            }

            if run_as && !run_as.to_s.empty?
              target['config'][transport] ||= {}
              target['config'][transport]['run-as'] = run_as
            end

            if run_as_command.is_a?(Array) && !run_as_command.empty?
              target['config'][transport] ||= {}
              target['config'][transport]['run-as-command'] = run_as_command
            end

            groups.each do |g|
              next unless g.is_a?(Hash)

              ts = g['targets'] || []
              target['vars']['enc_groups'] << g['name'] if ts.include?(certname)
            end

            targets << target
          end
        end

        targets
      end

      def error_payload(message, api_url:)
        {
          '_error' => {
            'msg'     => message,
            'kind'    => 'openvox_enc/api_error',
            'details' => { 'api_url' => api_url },
          },
        }
      end

      # HTTP GET /api/enc/inventory/bolt. Inject +http_client+ for tests.
      # http_client must respond to #get(uri, headers) -> object with #code and #body
      def fetch_inventory(api_url:, api_token: nil, ssl_verify: false, http_client: nil)
        base = api_url.to_s.sub(%r{/*$}, '')
        uri = URI.parse("#{base}/api/enc/inventory/bolt")
        headers = { 'Accept' => 'application/json' }
        headers['Authorization'] = "Bearer #{api_token}" if api_token && !api_token.empty?

        response = if http_client
                     http_client.get(uri, headers)
                   else
                     default_get(uri, headers, ssl_verify: ssl_verify)
                   end

        code = response.code.to_i
        unless code == 200
          raise "API returned HTTP #{code}: #{response.body}"
        end

        JSON.parse(response.body)
      end

      # Full resolve path used by the Bolt task.
      #
      # @return [Hash] { exit_code:, payload: }
      def resolve(params, http_client: nil)
        params = params.is_a?(Hash) ? params : {}

        api_url        = params['api_url'] || DEFAULT_API_URL
        group_filter   = params['group']
        transport      = params['transport'] || DEFAULT_TRANSPORT
        ssl_verify     = params.key?('ssl_verify') ? params['ssl_verify'] : false
        api_token      = params['api_token']
        token_file     = params['token_file'] || DEFAULT_TOKEN_FILE
        run_as         = params['run_as']
        run_as_command = params['run_as_command']

        token = resolve_token(api_token: api_token, token_file: token_file)

        begin
          inventory = fetch_inventory(
            api_url: api_url,
            api_token: token,
            ssl_verify: ssl_verify,
            http_client: http_client
          )
        rescue StandardError => e
          return {
            exit_code: 1,
            payload: error_payload(
              "Failed to query OpenVox GUI ENC API: #{e.message}",
              api_url: api_url
            ),
          }
        end

        targets = build_targets(
          inventory,
          group_filter: group_filter,
          transport: transport,
          run_as: run_as,
          run_as_command: run_as_command
        )

        { exit_code: 0, payload: { 'value' => targets } }
      end

      private

      def default_get(uri, headers, ssl_verify: false)
        http = Net::HTTP.new(uri.host, uri.port)
        if uri.scheme == 'https'
          http.use_ssl = true
          http.verify_mode = ssl_verify ? OpenSSL::SSL::VERIFY_PEER : OpenSSL::SSL::VERIFY_NONE
        end
        request = Net::HTTP::Get.new(uri.request_uri)
        headers.each { |k, v| request[k] = v }
        http.request(request)
      end
    end
  end
end
