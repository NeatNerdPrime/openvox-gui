# frozen_string_literal: true

# Minimal HTTP client double for OpenvoxEnc::Inventory.fetch_inventory.
# #get(uri, headers) -> object with #code and #body
class FakeHttp
  attr_reader :last_uri, :last_headers, :calls

  def initialize(code:, body:)
    @code = code
    @body = body
    @calls = 0
    @last_uri = nil
    @last_headers = nil
  end

  def get(uri, headers)
    @calls += 1
    @last_uri = uri
    @last_headers = headers
    Response.new(@code, @body)
  end

  class Response
    attr_reader :code, :body

    def initialize(code, body)
      @code = code
      @body = body
    end
  end
end
