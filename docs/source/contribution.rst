Contribution
============

We welcome you to `check the existing
issues <https://github.com/ITMO-NSS-team/GAMLET/issues>`__ for bugs or
enhancements to work on. If you have an idea for an extension to GAMLET,
please `file a new
issue <https://github.com/ITMO-NSS-team/GAMLET/issues/new>`__ so we can
discuss it.

Make sure to familiarize yourself with the project layout before making
any major contributions.


How to contribute
-----------------

The preferred way to contribute to GAMLET is to fork the `main
repository <https://github.com/ITMO-NSS-team/GAMLET/>`__ on GitHub:

1. Fork the `project repository <https://github.com/ITMO-NSS-team/GAMLET/>`__:
   click on the 'Fork' button near the top of the page. This creates a
   copy of the code under your account on the GitHub server.

2. Clone this copy to your local disk:

   ::

         $ git clone git@github.com:YourUsername/GAMLET.git
         $ cd GAMLET

3. Create a branch to hold your changes:

   ::

         $ git checkout -b my-contribution

4. Make sure your local environment is setup correctly for development.
   Installation instructions are almost identical to `the user
   instructions <instructions file>`__ except that GAMLET should *not* be
   installed. If you have GAMLET installed on your computer then make
   sure you are using a virtual environment that does not have GAMLET
   installed.

5. Start making changes on your newly created branch, remembering to
   never work on the ``main`` branch! Work on this copy on your
   computer using Git to do the version control.

6. To check your changes haven't broken any existing tests and to check
   new tests you've added pass run the following (note, you must have
   the ``nose`` package installed within your dev environment for this
   to work):

   ::

         $ pytest -s

7. When you're done editing and local testing, run:

   ::

         $ git add modified_files
         $ git commit

to record your changes in Git, then push them to GitHub with:

::

          $ git push -u origin my-contribution

Finally, go to the web page of your fork of the GAMLET repo, and click
'Pull Request' (PR) to send your changes to the maintainers for review.

(If it looks confusing to you, then look up the `Git
documentation <http://git-scm.com/documentation>`__ on the web.)

Before submitting your pull request
-----------------------------------

Before you submit a pull request for your contribution, please work
through this checklist to make sure that you have done everything
necessary so we can efficiently review and accept your changes.

If your contribution changes GAMLET in any way:

-  Update the
   `documentation <https://github.com/ITMO-NSS-team/GAMLET/tree/main/docs>`__
   so all of your changes are reflected there.

-  Update the
   `README <https://github.com/ITMO-NSS-team/GAMLET/blob/main/README.md>`__
   if anything there has changed.

If your contribution involves any code changes:

-  Update the `project unit
   tests <https://github.com/ITMO-NSS-team/GAMLET/tree/main/test>`__ to
   test your code changes.

-  Make sure that your code is properly commented with
   `docstrings <https://www.python.org/dev/peps/pep-0257/>`__ and
   comments explaining your rationale behind non-obvious coding
   practices.

If your contribution requires a new library dependency:

-  Double-check that the new dependency is easy to install via ``pip``
   or Anaconda and supports Python 3. If the dependency requires a
   complicated installation, then we most likely won't merge your
   changes because we want to keep GAMLET easy to install.

-  Add the required version of the library to
   `requirements.txt <https://github.com/ITMO-NSS-team/GAMLET/blob/main/requirements.txt>`__

Contribute to the documentation
-------------------------------
Take care of the documentation.

All the documentation is created with the Sphinx autodoc feature. Use ..
automodule:: <module_name> section which describes all the code in the module.

-  If a new package with several scripts:

   1. Go to `docs/source/gamlet <https://github.com/ITMO-NSS-team/GAMLET/tree/main/docs/source/gamlet>`__ and create new your_name_for_file.rst file.

   2. Add a Header underlined with “=” sign. It’s crucial.

   3. Add automodule description for each of your scripts. ::

       .. automodule:: "gamlet.your.first.script.path"
          :members:
          :undoc-members:
          :show-inheritance:

       .. automodule:: "gamlet.your.second.script.path"
          :members:
          :undoc-members:
          :show-inheritance:
       ...

   4. Add your_name_for_file to the toctree at docs/source/gamlet/index.rst

-  If a new module to the existed package:

    Most of the sections are already described in `docs/source/gamlet <https://github.com/ITMO-NSS-team/GAMLET/tree/main/docs/source/gamlet>`__ , so you can:

   -  choose the most appropriate and repeat 3-d step from the previous section.
   -  or create a new one and repeat 2-3 steps from the previous section.

-  If a new function or a class to the existing module:

    Be happy. Everything is already done for you.

After submitting your pull request
----------------------------------

After submitting your pull request,
`Travis-CI <https://travis-ci.com/>`__ will automatically run unit tests
on your changes and make sure that your updated code builds and runs on
Python 3. We also use services that automatically check code quality and
test coverage.

Check back shortly after submitting your pull request to make sure that
your code passes these checks. If any of the checks come back with a red
X, then do your best to address the errors.

Acknowledgements
----------------

This document guide is based at well-written `TPOT Framework
contribution
guide <https://github.com/EpistasisLab/tpot/blob/master/docs_sources/contributing.md>`__.