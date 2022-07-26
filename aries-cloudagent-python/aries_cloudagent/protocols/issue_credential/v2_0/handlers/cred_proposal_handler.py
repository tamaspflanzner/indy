"""Credential proposal message handler."""

from .....indy.issuer import IndyIssuerError
from .....ledger.error import LedgerError
from .....messaging.base_handler import BaseHandler, HandlerException
from .....messaging.request_context import RequestContext
from .....messaging.responder import BaseResponder
from .....storage.error import StorageError
from .....utils.tracing import trace_event, get_timer

from ..manager import V20CredManager, V20CredManagerError
from ..messages.cred_proposal import V20CredProposal


class V20CredProposalHandler(BaseHandler):
    """Message handler class for credential proposals."""

    async def handle(self, context: RequestContext, responder: BaseResponder):
        """
        Message handler logic for credential proposals.

        Args:
            context: proposal context
            responder: responder callback

        """
        r_time = get_timer()

        self._logger.debug("V20CredProposalHandler called with context %s", context)
        assert isinstance(context.message, V20CredProposal)
        self._logger.info(
            "Received v2.0 credential proposal message: %s",
            context.message.serialize(as_string=True),
        )

        if not context.connection_ready:
            raise HandlerException("No connection established for credential proposal")

        cred_manager = V20CredManager(context.profile)
        cred_ex_record = await cred_manager.receive_proposal(
            context.message, context.connection_record.connection_id
        )  # mgr only finds, saves record: on exception, saving state null is hopeless

        r_time = trace_event(
            context.settings,
            context.message,
            outcome="CredentialProposalHandler.handle.END",
            perf_counter=r_time,
        )

        # If auto_offer is enabled, respond immediately with offer
        if cred_ex_record.auto_offer:
            cred_offer_message = None
            try:
                (cred_ex_record, cred_offer_message) = await cred_manager.create_offer(
                    cred_ex_record,
                    counter_proposal=None,
                    comment=context.message.comment,
                )
                await responder.send_reply(cred_offer_message)
            except (V20CredManagerError, IndyIssuerError, LedgerError) as err:
                self._logger.exception(err)
                if cred_ex_record:
                    await cred_ex_record.save_error_state(
                        context.session(),
                        reason=err.message,
                    )
            except StorageError as err:
                self._logger.exception(err)  # may be logging to wire, not dead disk

            trace_event(
                context.settings,
                cred_offer_message,
                outcome="V20CredProposalHandler.handle.OFFER",
                perf_counter=r_time,
            )