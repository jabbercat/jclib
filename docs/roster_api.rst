Roster API
##########

This is a brain-storming document for the generic and extensible API provided
for the roster by base mlxc (not Qt or Urwid or any other interface).

The API and by extension the objects providing and extending the API must
provide the following features:

* Be mappable to XML, and loadable from XML, for local storage
* Provide a full mapping of the roster capabilities of stock XMPP
* Extensible for plugins to add custom, possibly synced roster entries
* Extensible for plugins and frontend implementations to override parts of the
  implementation for their own needs. This includes but is not limited to:

  * Monitoring and modifying any addition and removal of child entries
  * Monitoring changes in attributes of entries
  * Making changes to the attributes of entries

* A simple API for custom roster entry synchronization


Node API
--------

The goal of this API is to provide all methods and entry points neccessary for
plugins to extend the roster with the above functionality.

This is still drafty. As noted below, the class hierarchy is yet to be
designed.

.. method:: RosterNode._add_to_parent(new_parent)

   Prepare insertion into current parent. This needs to do anything which is
   required by a parent object to insert this specific object. In
   particular, it is required to register any vias held by this object.

.. method:: RosterNode._remove_from_parent(old_parent)

   Prepare removal from the current parent. This needs to do anything which is
   required by a parent object to remove this specific object. In
   particular, it is required to unregister any vias held by this object.

Synchronization API
-------------------

The synchronization API will be based on XEP-0049 and a custom protocol for
notifications in the first iteration. As soon as XEP-0163 and XEP-0223 land in
some XMPPd I test against, we can move on to support that if the XMPPd supports
it.

The algorithm to avoid race conditions when using XEP-0049 still needs to be
defined.

Ideally, we would provide an API for the synchronization API somewhere else and
make the Roster only provide a layer of abstraction for that.

.. classmethod:: Roster.register_synced_data_tag(tag, func)

   Register a data tag which relates to the roster and is stored in private XML
   storage.

   *func* is called whenever a child element of the data root tag in the private
   XML storage is modified by a remote MLXC client. The roster instance, a
   string indicating the type of operation and the XML element which was
   modified are passed as arguments. The string is one of ``"inserted"``,
   ``"modified"`` or ``"removed"``.

   A simplistic implementation may treat a *modified* event as a *removed* event
   followed by an *inserted* event.

.. method:: Roster.insert_synced_data(tag, el)

   Insert the given element *el* into the synchronized storage under the root
   element *tag*.

.. method:: Roster.update_synced_data(tag, el)

   Insert the given element *el* into the synchronized storage, replacing any
   element with the same id attribute.

.. method:: Roster.remove_synched_data(tag, id)

   Remove the element with the given *id* from the synchronized storage.
